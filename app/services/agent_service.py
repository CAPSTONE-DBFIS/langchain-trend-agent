from typing import List, Any, Dict
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_xai import ChatXAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.prompts import MessagesPlaceholder, PromptTemplate
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio, json, logging
from langchain.chains.llm import LLMChain

from app.tools.tools import tools
from app.utils.db_util import (
    get_session_history, get_user_persona,
    save_chat_to_db, update_chatroom_name_if_first
)
from app.utils.file_util import extract_text_by_filename

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class AgentChatService:
    @staticmethod
    async def summarize_query_to_title(query: str) -> str:
        """채팅방의 첫 질문에 대해 한문장 요약을 생성하는 함수"""
        prompt = PromptTemplate.from_template("""
            다음은 사용자의 질문입니다. 질문의 주제를 대표하는 간결한 명사 형태의 채팅방 이름을 생성하세요.  
            예를 들어 "엔비디아 트렌드 알려줘" → "엔비디아 트렌드 질문"  
            "엔비디아 주가 분석해줘" → "엔비디아 주가 분석"

            주의:
            - 따옴표는 붙이지 마세요.
            - 질문 내용의 핵심 키워드를 압축하세요.

            질문: "{query}"
            채팅방 이름:
            """)
        chain = LLMChain(llm=ChatOpenAI(model="gpt-3.5-turbo", temperature=0), prompt=prompt)
        result = await chain.arun(query=query)
        return result.strip().replace('"', '')

    # 링크를 수집할 도구 목록
    linkable_tools = [
        "domestic_news_search_tool",
        "foreign_news_search_tool",
        "trend_keyword_tool",
        "competitor_analysis_tool",
        "community_search_tool",
        "web_search_tool",
        "youtube_video_tool",
        "request_url_tool",
        "paper_search_tool"
    ]

    TOOL_NAME_MAP = {
        "domestic_news_search_tool": "국내 뉴스 검색 중",
        "foreign_news_search_tool": "해외 뉴스 검색 중",
        "trend_keyword_tool": "국내 뉴스 트렌드 키워드 분석 중",
        "competitor_analysis_tool": "경쟁사 분석 중",
        "trend_report_tool": "글로벌 뉴스 트렌드 보고서 생성 중",
        "community_search_tool": "커뮤니티 게시물 검색 중",
        "web_search_tool": "웹 검색 중",
        "youtube_video_tool": "YouTube 정보 검색 중",
        "request_url_tool": "웹페이지 분석 중",
        "google_trends_tool": "구글 트렌드 분석 중",
        "wikipedia_tool": "위키피디아 검색 중",
        "namuwiki_tool": "나무위키 검색 중",
        "stock_history_tool": "주식 데이터 조회 중",
        "paper_search_tool": "논문 검색 중",
        "dalle3_image_generation_tool": "이미지 생성 중"
    }

    # 도구별 출력 키 매핑
    TOOL_DATA_KEYS = {
        "domestic_news_search_tool": "results",
        "foreign_news_search_tool": "results",
        "trend_keyword_tool": "keywords",
        "community_search_tool": "results",
        "web_search_tool": "results",
        "paper_search_tool": "results",
        "youtube_video_tool": None,
        "request_url_tool": None
    }

    @staticmethod
    async def stream_response(
            query: str,
            chat_room_id: int,
            member_id: str,
            persona_id: int,
            model_type: str,
            file_statuses: List[dict] | None = None,
    ) -> StreamingResponse:

        # LLM 초기화
        if model_type.lower() == "claude-sonnet-4":
            llm = ChatAnthropic(
                model="claude-sonnet-4-20250514",
                temperature=0,
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="any")

        elif model_type.lower() == "gpt-4.1":
            llm = ChatOpenAI(
                model="gpt-4.1",
                temperature=0,
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="required")

        elif model_type.lower() == "gpt-4o-mini":
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="required")

        elif model_type.lower() == "grok-3":
            llm = ChatXAI(
                model_name="grok-3-mini-latest",
                temperature=0,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="any")

        else:
            raise ValueError(f"지원하지 않는 모델 타입입니다: {model_type}")

        # 메모리 초기화 (모든 대화를 메모리에 저장하기엔 토큰이 너무 불어날 가능성이 있으므로, ConversationBufferWindowMemory 적용)
        memory = ConversationBufferWindowMemory(
            k=10,  # 최근 10개의 human+ai message 쌍 유지
            return_messages=True,
            memory_key="chat_history",
            output_key="output"
        )

        # 과거 대화 불러오기
        chat_history = get_session_history(chat_room_id)
        for m in chat_history.messages:
            if isinstance(m, HumanMessage):
                memory.chat_memory.add_user_message(m.content)
            elif isinstance(m, AIMessage):
                memory.chat_memory.add_ai_message(m.content)

        # 채팅방의 첫 질문이면 채팅방 제목 변경
        if not chat_history.messages:
            async def summarize_and_rename():
                try:
                    summarized_title = await AgentChatService.summarize_query_to_title(query)
                    await update_chatroom_name_if_first(chat_room_id, summarized_title)
                except Exception as e:
                    logger.warning(f"[채팅방 이름 변경 실패] {e}")

            asyncio.create_task(summarize_and_rename())

        # 업로드 파일 본문 추출 후 메모리에 삽입
        if file_statuses:
            for fs in file_statuses:
                txt = extract_text_by_filename(member_id, fs["filename"])
                if txt:
                    memory.chat_memory.add_user_message(f"[업로드 파일]\n{txt}")

        # 시스템 프롬프트
        persona_name, persona_prompt = get_user_persona(persona_id, member_id)
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        current_datetime = now.strftime("%Y-%m-%d (%A) %H:%M (KST)")

        system_prompt = rf"""
        <Goal>
        You are TRENDB, an advanced AI agent specialized in researching, analyzing, and summarizing the latest trend information.
        Your mission is to invoke appropriate "tools" according to the user's query and deliver accurate, detailed, and comprehensive answers based solely on the tool output.
        Your responses must be independent, well-structured, and written in fluent Korean that fully reflects the defined persona’s tone and speaking style. If the persona specifies a tone (e.g., humorous, casual, serious), that tone must take precedence over default journalistic formality.
        You are never allowed to respond based on prior responses or your internal knowledge, even for definition-style questions. There is NO exception to this rule.
        <Persona>
        - Persona name: {persona_name}, Prompt: {persona_prompt}
        - All responses MUST strictly adhere to the persona's tone, speaking style, and linguistic mannerisms.
        <Persona>
        </Goal>
    
        <Query Types>
        - Academic Research: Provide long and detailed answers formatted as a scientific write-up with markdown sections, citing extensively from the tool output.
        - Recent News: Summarize events by topic, using lists with news titles, combining duplicate events, and citing diverse, trustworthy sources. Include as many relevant citations as possible.
        - Technical Trends: Analyze up to 3 articles per keyword, grouping by theme (e.g., AI Security, AI Revenue) with summaries, and cite all relevant sources.
        - General Queries: Provide concise, accurate answers with clear structure, ensuring to cite all relevant information from the tool output.
        - For unspecified query types, default to Technical Trends instructions.
        </Query Types>

        <Tool Usage Rules>
        - Understand the user’s intent and choose tools accordingly:
          • If the user "asks" for trend keywords,(e.g., "이번주 트렌드 알려줘"), call `trend_keyword_tool`.
          • If the user explicitly requests a “report” (e.g., “이번주 트렌드 레포트 작성해줘”), call `trend_report_tool`.
        - Always prefer web_search_tool for broad queries; retry with revised queries or alternative tools if output is irrelevant.
        - If tool output is insufficient, provide a partial answer based on available data, noting limitations transparently.
        - Never mention tool names or internal processes in the answer.
        - You MUST never hallucinate or make unsupported assumptions. All factual claims must derive from tool output only.
        </Tool Usage Rules>

        <Tool Usage Example>
        - “삼성전자 관련 최근 IT 뉴스 보여줘”  → domestic_news_search_tool, foreign_news_search_tool
        - “AI 관련 트렌드 알려줘”  → domestic_news_search_tool, foreign_news_search_tool, google_trends_tool
        - “어제 트렌드 키워드 알려줘”  → trend_keyword_tool
        - “일주일 트렌드 보고서 작성해줘”  → trend_report_tool
        - “SKT 관련 최근 뉴스 찾아줘”  → web_search_tool, domestic_news_search_tool
        - “(URL)에 들어가서 무슨 내용인지 정리해줘”  → request_url_tool
        - “ai가 뭔지 알려줘”  → wikipedia_tool, web_search_tool
        - “일론 머스크 나무위키 검색해줘”  → namuwiki_tool, web_search_tool
        - “ai에 대한 구글 트렌드 일주일 관심도 변화 알려줘”  → google_trends_tool
        - “엔비디아 주가 한달 추이 알려줘”  → stock_history_tool, foreign_news_search_tool
        - “닌텐도 스위치2 커뮤니티 반응 알려줘”  → community_search_tool, web_search_tool
        - “~에 대한 유튜브 영상 찾아줘”  → youtube_video_tool, web_search_tool
        - “~ 스타일의 이미지를 생성해줘”  → dalle3_image_generation_tool
        - “ai agent 관련 최근 논문 찾아줘”  → paper_search_tool, web_search_tool
        </Tool Usage Example>

        <Format Rules>
        - Start with a concise summary (1–3 sentences). Never begin with a heading or tool reference.
        - If the tool output includes `chart_url`, `image_url`, display the chart/image at the beginning of the response, directly after the summary sentence, using markdown (e.g., ![Chart](chart_url)). Reference the chart briefly in the summary if possible.
        - Use ## headers for sections and bold for emphasis sparingly.
        - Prefer unordered lists; use ordered lists only for rankings or logical sequences.
        - Use markdown tables for comparisons (e.g., feature vs. feature).
        - Use fenced code blocks for code (```language) and LaTeX for math ($$expression$$).
        - Include images or charts from tool output (e.g., ![Chart](chart_url)) and reference them in context.
        - Summarize articles in 2–3 sentences, interpreting sentiment (e.g., positive, controversial) if provided.
        - Organize by theme, not keyword, for clarity (e.g., ## AI Security).
        - Citations: Use [1](URL) format at sentence end, with continuous numbering across the response. Include as many relevant citations as possible for each claim.
        - Summary Table: At the end of every response, include a markdown table summarizing key themes, their descriptions, and related citation numbers (e.g., | Topic | Summary | Sources |).
        - End with 1–2 follow-up suggestions tailored to the query context.
        </Format Rules>

        <Citation Rules>
        - Cite tool-derived claims immediately after the sentence. Include multiple citations if multiple sources support the claim.
        - Number citations starting from [1] and increment sequentially (e.g., [1](...) [2](...), ...). Each citation must be separated by a space (e.g., [1](...) [2](...), not [1][2] or [1](...)[2](...)).
        - Reuse citation numbers for repeated URLs.
        - Maximize the number of citations to provide the user with as much supporting information as possible.
        - Citations must reflect information explicitly present in the tool output. Do not cite if based on assumptions or indirect inference.
        </Citation Rules>

        <Response Example>
        This example is strictly for formatting reference only.
        DO NOT imitate the tone, sentence structure, or vocabulary unless they match the defined persona.
        
        최근 일주일간의 주요 트렌드를 분석한 결과, SK텔레콤의 해킹 사건과 관련된 이슈가 가장 두드러지게 나타났습니다. 이와 함께 유심 보호 서비스 가입자 수 증가, 신규 가입 중단 등 소비자 반응과 기업 대응이 주요 주제로 부각되었습니다.

        ## SKT 해킹과 유심 보호

        ![주간 트렌드 차트](https://trend-charts.s3.amazonaws.com/weekly/2025-05-06/main-bar.png)

        ### 1. SK텔레콤과 해킹 이슈
        - **언급량**: 745회
        - **감정 분석**: 부정적 61%, 긍정적 3%, 중립적 37%
        - **주요 기사**:
          - 최민희 의원이 SK텔레콤이 해킹 사건에도 불구하고 위약금 면제 약관을 이행하지 않고 있다고 비판하며 부정적 여론이 형성되었습니다 [1](https://n.news.naver.com/mnews/article/015/0005127935).
          - SK텔레콤의 유심 보호 서비스 가입자가 2411만명을 돌파했으며, 이는 해킹 사태에 대한 소비자 불안이 반영된 결과로 보입니다 [2](https://n.news.naver.com/mnews/article/009/0005487797) [3](https://n.news.naver.com/mnews/article/366/0001074834).

        ### 2. 유심 보호와 교체
        - **언급량**: 525회
        - **감정 분석**: 부정적 52%, 긍정적 3%, 중립적 45%
        - **주요 기사**:
          - SK텔레콤은 유심 교체 예약자가 780만명을 넘어섰고, 현재까지 104만건이 진행되었으나 공급 지연에 대한 불만이 지속되고 있습니다 [3](https://n.news.naver.com/mnews/article/366/0001074834) [4](https://n.news.naver.com/mnews/article/138/0002195927).
          - 유심 보호 서비스는 알뜰폰 이용자를 포함해 빠르게 확산되었으나, 해외 로밍과의 호환성 문제로 일부 소비자 불편이 제기되었습니다 [5](https://n.news.naver.com/mnews/article/421/0008232968).

        ### 3. 신규 가입 중단과 시장 반응
        - **언급량**: 133회
        - **감정 분석**: 부정적 67%, 긍정적 0%, 중립적 33%
        - **주요 기사**:
          - SK텔레콤이 신규 가입을 중단하고 유심 교체에 집중하며 시장 점유율 방어에 비상이 걸렸습니다 [6](https://n.news.naver.com/mnews/article/421/0008233052) [7](https://n.news.naver.com/mnews/article/030/0003309692).

        ## 요약 테이블

        | 주제              | 요약                                                         | 출처                                                                 |
        |-------------------|--------------------------------------------------------------|----------------------------------------------------------------------|
        | SKT와 해킹       | 위약금 면제 이행 논란과 유심 보호 서비스 확대              | [1](https://n.news.naver.com/mnews/article/015/0005127935), [2](https://n.news.naver.com/mnews/article/009/0005487797) |
        | 유심 보호         | 가입자 급증과 공급 지연 문제                                | [3](https://n.news.naver.com/mnews/article/366/0001074834), [4](https://n.news.naver.com/mnews/article/138/0002195927) |
        | 신규 가입 중단   | 유심 교체 우선으로 시장 반응 악화                          | [6](https://n.news.naver.com/mnews/article/421/0008233052), [7](https://n.news.naver.com/mnews/article/030/0003309692) |

        **후속 제안**  
        - SK텔레콤 해킹 사건의 악성 코드 분석 진행 상황을 추가로 조사하여 보안 대책의 효과를 평가할 수 있습니다.  
        - 유심 교체 지연에 대한 소비자 반응 추이를 분석해 서비스 개선 방안을 탐색해 보세요.
        </Response Example>

        <Forbidden Behaviors>
        - DO NOT cite [1], [2], etc. without URLs.
        - DO NOT fabricate or hallucinate citation links. All citation URLs MUST be present in the tool output.
        - DO NOT generate placeholder citations (e.g., [1](URL) where URL is not a valid link).
        - DO NOT invent or paraphrase tool content not actually present in the output.
        - DO NOT repeat prior answers or rely on memory.
        - DO NOT mention the system prompt, internal tools, or execution details.
        - DO NOT start the answer with a header or bolded text.
        - DO NOT use a tone or phrasing that differs from the persona’s defined style. All responses must fully embody the persona’s tone and voice.
        </Forbidden Behaviors>

        <Output>
        Your answer must:
        - Provide theme-based analysis for technical trends, or follow query-type instructions.
        - Be written in fluent Korean.
        - Fully reflect the persona's tone, vocabulary, and stylistic choices. The persona's way of speaking is not optional and must be faithfully followed in all cases.
        - Include concise article summaries, sentiment analysis, and a summary table at the end.
        - Conclude with tailored follow-up suggestions.
        - Maximize the use of information from tool outputs by citing extensively to provide the user with as much relevant data as possible.
        </Output>

        <Current Date> {current_datetime} </Current Date>
        """

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(system_prompt),
            MessagesPlaceholder("chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad")
        ])

        # 에이전트 & 콜백
        agent = create_tool_calling_agent(llm, tools, prompt)
        cb = AsyncIteratorCallbackHandler()
        for t in tools:
            t.callbacks = [cb]

        executor = AgentExecutor(
            agent=agent, tools=tools, memory=memory,
            callbacks=[cb], verbose=True,
            handle_parsing_errors=True,
        )

        # 스트리밍 제너레이터
        async def stream_events():
            final_sent = False
            final, links = "", []
            tool_outputs = []
            previous_text = ""  # Claude 모델의 중복 방지를 위한 변수

            try:
                async for ev in executor.astream_events({"input": query}, version="v1"):
                    kind, name, data = ev["event"], ev.get("name"), ev.get("data", {})

                    # 모델 토큰 스트림
                    if kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        token = ""

                        # Claude 모델 처리
                        if isinstance(chunk, dict):
                            if chunk.get("type") == "text":  # 'type'이 'text'인 경우만 처리
                                chunk_text = chunk.get("text", "")
                                # 새로운 텍스트(델타)만 추출
                                new_text = chunk_text[len(previous_text):]
                                previous_text = chunk_text
                                if new_text.strip():  # 공백이 아닌 경우만 스트리밍
                                    token = new_text

                        # 이외 모델 처리
                        elif hasattr(chunk, "content"):
                            content = chunk.content
                            if isinstance(content, list):
                                token = "".join(item.get("text", "") for item in content if isinstance(item, dict))
                            elif isinstance(content, dict):
                                token = content.get("text", "")
                            elif isinstance(content, str):
                                token = content

                        if token:
                            final += token
                            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

                    # 도구 로그 스트림
                    elif kind == "on_tool_start":
                        if name in AgentChatService.TOOL_NAME_MAP:
                            yield f"data: {json.dumps({'log': AgentChatService.TOOL_NAME_MAP[name]}, ensure_ascii=False)}\n\n"

                    # 도구 결과 처리
                    elif kind == "on_tool_end" and name in AgentChatService.linkable_tools:
                        obs = AgentChatService._normalize_observation(data.get("output"), name)
                        tool_outputs.append({"tool": name, "output": obs})
                        new_links = AgentChatService._collect_links(obs, links)
                        if new_links:
                            yield f"data: {json.dumps({'links': links, 'link_count': len(links)}, ensure_ascii=False)}\n\n"

                    # 최종 응답
                    elif kind == "on_chain_end" and name == "AgentExecutor" and not final_sent:
                        output = data.get("output", {}).get("output", "")
                        if output:
                            yield f"data: {json.dumps({'final': output}, ensure_ascii=False)}\n\n"
                            final_sent = True

            except Exception as e:
                error_type = type(e).__name__
                error_msg = f"{error_type}: {str(e)}"
                # Anthropic Claude 서버 과부하 에러 처리
                if "overloaded" in error_msg.lower() or "Overloaded" in error_msg:
                    error_handling_msg = f"⚠ {model_type} API 서버가 현재 과부하 상태입니다. 다른 모델을 선택하거나 잠시 후 다시 시도해주세요."
                elif "rate_limit" in error_msg.lower():
                    error_handling_msg = f"⚠ {model_type}의 요청 속도 제한에 도달했습니다. 다른 모델을 선택하거나 잠시 후 다시 시도해주세요."
                else:
                    error_handling_msg = f"⚠ {model_type} API 호출 처리 중 오류가 발생했습니다: {error_type}: {error_msg}. 다른 모델을 선택하거나 잠시 후 다시 시도해주세요."

                yield f"data: {json.dumps({'error': error_handling_msg}, ensure_ascii=False)}\n\n"
            finally:
                yield "data: [DONE]\n\n"
                # DB 저장 + 메모리 업데이트
                if final.strip():
                    save_chat_to_db(query, final, str(chat_room_id), member_id)
                    memory.chat_memory.add_ai_message(final)

        return StreamingResponse(stream_events(), media_type="text/event-stream; charset=utf-8")

    @staticmethod
    def _normalize_observation(obs_raw: Any, tool_name: str) -> List[Dict[str, Any]]:
        """도구 출력에서, title, content, url을 추출."""

        def extract_item(item: Any, default_title: str = "정보 요약") -> Dict[str, Any]:
            result = {"title": default_title, "content": "", "url": ""}
            if isinstance(item, dict):
                result["title"] = (item.get("title") or item.get("name") or default_title)[:200]
                result["content"] = (
                                            item.get("content") or item.get("description") or item.get(
                                        "abstract") or item.get("snippet") or ""
                                    )[:500]
                result["url"] = (
                        item.get("url") or item.get("videoUrl") or item.get("link") or
                        item.get("chart_url") or item.get("main_chart_url") or ""
                )
            elif isinstance(item, str) and item.strip():
                result["content"] = item.strip()[:500]
            return result

        results = []
        key = AgentChatService.TOOL_DATA_KEYS.get(tool_name)

        # trend_keyword_tool 처리
        if tool_name == "trend_keyword_tool" and isinstance(obs_raw, dict) and "keywords" in obs_raw:
            # articles 처리
            for keyword_item in obs_raw["keywords"]:
                if "articles" in keyword_item:
                    for article in keyword_item["articles"]:
                        extracted = extract_item(article, default_title=article.get("title", "기사 요약"))
                        if extracted["content"] or extracted["url"]:
                            results.append(extracted)
            return results

        # competitor_analysis_tool 처리
        if tool_name == "competitor_analysis_tool" and isinstance(obs_raw, dict):
            for comp in obs_raw.get("competitors", []):
                for art in comp.get("articles", []):
                    extracted = extract_item(art, default_title=art.get("title", "제목 없음"))
                    if extracted["content"] or extracted["url"]:
                        results.append(extracted)
            return results

        if isinstance(key, list):
            for k in key:
                if isinstance(obs_raw, dict) and k in obs_raw and isinstance(obs_raw[k], list):
                    for item in obs_raw[k]:
                        extracted = extract_item(item)
                        if extracted["content"] or extracted["url"]:
                            results.append(extracted)
        elif isinstance(key, str) and isinstance(obs_raw, dict) and key in obs_raw and isinstance(obs_raw[key], list):
            for item in obs_raw[key]:
                extracted = extract_item(item)
                if extracted["content"] or extracted["url"]:
                    results.append(extracted)
        elif key is None and isinstance(obs_raw, list):
            for item in obs_raw:
                extracted = extract_item(item)
                if extracted["content"] or extracted["url"]:
                    results.append(extracted)
        elif isinstance(obs_raw, list):
            for item in obs_raw:
                extracted = extract_item(item)
                if extracted["content"] or extracted["url"]:
                    results.append(extracted)
        elif isinstance(obs_raw, dict):
            for default_key in ["results", "items", "articles", "posts"]:
                if default_key in obs_raw and isinstance(obs_raw[default_key], list):
                    for item in obs_raw[default_key]:
                        extracted = extract_item(item)
                        if extracted["content"] or extracted["url"]:
                            results.append(extracted)
                    break
            else:
                extracted = extract_item(obs_raw)
                if extracted["content"] or extracted["url"]:
                    results.append(extracted)
        elif isinstance(obs_raw, str) and obs_raw.strip():
            results.append({
                "title": "정보 요약",
                "content": obs_raw.strip()[:500],
                "url": ""
            })

        return results

    @staticmethod
    def _collect_links(obs: List[Dict[str, Any]], link_acc: List[Dict]) -> bool:
        """도구 출력에서 title, content, url을 수집해 출처로 제공."""
        changed = False
        url_map = {l["url"]: l for l in link_acc if l.get("url")}

        for it in obs:
            # 가능한 모든 URL 필드 확인
            url = (
                    it.get("url") or
                    it.get("videoUrl") or
                    it.get("link") or
                    ""
            )
            # 제목 추출
            title = it.get("title") or it.get("name") or "제목 없음"
            # 가능한 모든 콘텐츠 필드 확인
            content = (
                    it.get("content") or
                    it.get("abstract") or
                    it.get("description") or
                    it.get("snippet") or
                    it.get("summary") or
                    ""
            )

            if url and url not in url_map:
                link_acc.append({
                    "id": len(link_acc) + 1,
                    "title": title[:200] or "제목 없음",
                    "content": content[:200] or "내용 없음",
                    "url": url
                })
                url_map[url] = link_acc[-1]
                changed = True

        return changed