import asyncio
import datetime
from dotenv import load_dotenv
from typing import List, Dict, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

# 툴
from app.tools.tools import reddit_tool, youtube_video_tool, search_web_tool, naver_blog_tool, daum_blog_tool, articles_tool

# PostgreSQL에서 대화 기록 및 페르소나 가져오기
from app.utils.db import get_session_history, get_user_persona

load_dotenv()

# LLM 설정
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# 상태 관리
class SearchState(BaseModel):
    input_query: str
    search_type: Optional[str] = None
    news_results: List[Dict[str, str]] = []
    community_results: List[Dict[str, str]] = []
    web_results: List[Dict[str, str]] = []
    chat_history: str = ""
    persona_prompt: str = ""
    rag_response: str = ""

workflow = StateGraph(SearchState)

# PostgreSQL에서 대화 기록 및 페르소나 가져오기
async def fetch_user_data(state: SearchState, config: Optional[RunnableConfig] = None):
    if not config or "configurable" not in config:
        raise ValueError("configurable 키가 포함된 RunnableConfig가 필요합니다.")

    configurable = config["configurable"]
    chat_room_id = configurable.get("chat_room_id", "")
    member_id = configurable.get("member_id", "")

    if not chat_room_id or not member_id:
        raise ValueError("chat_room_id 또는 member_id가 누락되었습니다.")

    chat_history = get_session_history(chat_room_id)
    persona_prompt = get_user_persona(member_id)

    chat_history_text = "\n".join(
        [
            f"User: {msg.content}" if isinstance(msg, HumanMessage) else f"AI: {msg.content}"
            for msg in chat_history.messages
        ]
    )

    return state.model_copy(update={"chat_history": chat_history_text, "persona_prompt": persona_prompt})

workflow.add_node("fetch_user_data", fetch_user_data)
workflow.set_entry_point("fetch_user_data")
workflow.add_edge("fetch_user_data", "classify_search_type")

# 검색 유형 분류
async def classify_search_type(state: SearchState):
    classification_prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="사용자의 질문을 분석하여 적절한 검색 유형을 선택하세요."),
        SystemMessage(content="""
        - "news": 뉴스 검색이 필요한 경우
        - "community": 커뮤니티 검색이 필요한 경우 (Reddit, Daum, Naver Blog)
        - "web": 웹 검색이 필요한 경우 (Tavily, YouTube)
        - "all": 모든 검색이 필요한 경우
        - "none": 검색이 필요 없는 경우
        """),
        HumanMessage(content=f"사용자의 질문: {state.input_query}")
    ])

    response = await llm.ainvoke(classification_prompt.format())
    predicted_type = response.content.strip().lower().replace('"', '').replace("'", "")

    valid_types = {"news", "community", "web", "all"}
    search_type = predicted_type if predicted_type in valid_types else "news"

    return state.model_copy(update={"search_type": search_type})

workflow.add_node("classify_search_type", classify_search_type)

# 뉴스 검색 (News)
async def search_news_task(state: SearchState):
    tasks = [
        asyncio.to_thread(search_web_tool, state.input_query, 5),
        asyncio.to_thread(articles_tool, state.input_query)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    news_results = sum([res if isinstance(res, list) else [] for res in results], [])

    # score 값을 문자열로 변환
    for item in news_results:
        if "score" in item and isinstance(item["score"], float):
            item["score"] = str(item["score"])

    return state.model_copy(update={"news_results": news_results})

workflow.add_node("search_news_task", search_news_task)

# 커뮤니티 검색 (Community)
async def search_community_task(state: SearchState):
    tasks = [
        asyncio.to_thread(reddit_tool, state.input_query, 5, 30),
        asyncio.to_thread(daum_blog_tool, state.input_query, 5),
        asyncio.to_thread(naver_blog_tool, state.input_query, 5, 30)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return state.model_copy(update={"community_results": sum([res if  isinstance(res, list) else [] for res in results], [])})

workflow.add_node("search_community_task", search_community_task)

# 웹 검색 (Web)
async def search_web_task(state: SearchState):
    tasks = [
        asyncio.to_thread(search_web_tool, state.input_query, 5),
        asyncio.to_thread(youtube_video_tool, state.input_query, 5)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return state.model_copy(update={"web_results": sum([res if isinstance(res, list) else [] for res in results], [])})

workflow.add_node("search_web_task", search_web_task)

# 검색 결과 요약
async def summarize_results(state: SearchState):
    # score 값을 문자열로 변환 (중복 변환 방지)
    for item in state.news_results:
        if "score" in item and isinstance(item["score"], float):
            item["score"] = str(item["score"])

    context = f"""
    - 뉴스 검색 결과: {state.news_results}
    - 커뮤니티 검색 결과: {state.community_results}
    - 웹 검색 결과: {state.web_results}
    """

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content="[역할]:\n"
                              "당신은 DB FIS 임직원들에게 업계 트렌드 정보를 제공하는 챗봇 TRENDB 입니다.\n"
                              "사용자의 질문에 대해 최신 트렌드 및 시장 분석 정보를 제공해야 합니다."),

        SystemMessage(content=f"[페르소나 스타일]:\n"
                              "당신은 다음과 같은 스타일로 답변해야 합니다:\n"
                              f"{state.persona_prompt}\n"
                              "이 스타일을 철저히 유지하면서 답변을 작성하세요."),

        SystemMessage(content="[답변 지침]:\n"
                              "1. 검색된 정보를 최대한 활용하여 사용자 질문에 답변하세요.\n"
                              "2. 대화 기록을 참고하여 사용자와의 맥락을 반영하세요.\n"
                              "3. 문체와 말투는 위의 페르소나 스타일을 유지해야 합니다.\n"
                              "4. 페르소나와 맞지 않는 건조한 설명을 피하고, 친근하고 자연스러운 표현을 사용하세요.\n"
                              "5. 답변의 근거를 문서에서 찾았다면 출처를 함께 기재해주세요."),

        HumanMessage(content=f"[대화 기록]:**\n{state.chat_history}"),
        HumanMessage(content=f"[검색된 정보]:**\n{context}"),
        HumanMessage(content=f"[사용자 질문]:**\n{state.input_query}")
    ])

    response = await llm.ainvoke(prompt.format())
    return state.model_copy(update={"rag_response": response.content})

workflow.add_node("summarize_results", summarize_results)

# 워크플로우 연결
workflow.add_conditional_edges(
    "classify_search_type",
    lambda state: state.search_type,
    {
        "news": "search_news_task",
        "community": "search_community_task",
        "web": "search_web_task",
        "all": "search_news_task",
        "none": "summarize_results"  #검색이 필요 없으면 바로 요약으로 이동
    },
)

workflow.add_edge("search_news_task", "summarize_results")
workflow.add_edge("search_community_task", "summarize_results")
workflow.add_edge("search_web_task", "summarize_results")

executor = workflow.compile()

async def run_search_workflow(input_query: str, chat_room_id: str, member_id: str):
    initial_state = SearchState(input_query=input_query)
    config = RunnableConfig(configurable={"chat_room_id": chat_room_id, "member_id": member_id})
    response = await executor.ainvoke(initial_state, config=config)
    return response.get("rag_response", "응답이 없습니다.")