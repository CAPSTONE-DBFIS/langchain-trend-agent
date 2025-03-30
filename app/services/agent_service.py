from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.prompts import MessagesPlaceholder
from app.tools.tools import reddit_tool, youtube_video_tool, search_web_tool, naver_blog_tool, daum_blog_tool, articles_tool, google_trending_tool, wikipedia_tool, translation_tool, request_url_tool, generate_trend_report_tool
from app.utils.db import get_session_history, get_user_persona
from datetime import datetime

# 환경 변수 로드
load_dotenv()

# 사용자 요청 처리 함수 (ReAct 방식)
def process_query(user_query: str, chat_room_id: str, member_id: str):
    """
    LLM이 필요한 검색 도구를 실행하고, 검색 결과를 반영하여 답변을 생성하는 함수.
    """
    # LLM 설정
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # 대화 기록 메모리 설정
    memory = ConversationBufferMemory(return_messages=True, memory_key="chat_history")

    # 검색 도구 (LangChain Agents용 Tool 정의)
    tools = [search_web_tool, articles_tool, reddit_tool, daum_blog_tool, naver_blog_tool,
             youtube_video_tool, google_trending_tool, wikipedia_tool, translation_tool, request_url_tool, generate_trend_report_tool]

    # PostgreSQL에서 대화 기록 및 페르소나 가져오기
    chat_history = get_session_history(chat_room_id)
    persona_prompt = get_user_persona(member_id)

    # DB에서 가져온 대화 기록을 LangChain 메모리에 삽입
    for msg in chat_history.messages:
        if isinstance(msg, HumanMessage):
            memory.chat_memory.add_user_message(msg.content)
        elif isinstance(msg, AIMessage):
            memory.chat_memory.add_ai_message(msg.content)

    # 현재 날짜와 시간을 가져옴
    current_datetime = datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")

    prompt = ChatPromptTemplate.from_messages([
        ("system", f"당신은 DB FIS 임직원들에게 업계 트렌드 정보를 제공하는 챗봇 TRENDB 입니다. "
                   f"당신의 임무는 사용자의 질문을 분석하고, 필요한 정보를 검색하여 답변하는 것입니다. "
                   f"DB FIS의 주요 경쟁사는 다음과 같습니다: 삼성SDS, LG CNS, 현대오토에버, SK C&C, 롯데정보통신, 포스코DX, 미라콤아이앤씨, 메가존클라우드, 한화시스템, CJ올리브네트웍스  "
                   f"유저가 선택한 페르소나를 기반으로 응답 스타일을 맞추세요.\n\n💡 [페르소나] {persona_prompt}"
                   f"현재 날짜와 시간은 {current_datetime} 입니다."),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    #tool calling agent 생성
    agent = create_tool_calling_agent(llm, tools, prompt)

    # AgentExecutor 생성
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

    # AgentExecutor 실행 및 응답 받기
    result = agent_executor.invoke({"input": user_query})

    # run_agent 실행 후 결과 반환
    return result["output"]