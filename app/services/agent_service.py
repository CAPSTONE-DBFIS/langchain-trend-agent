from __future__ import annotations

import os
from typing import List, Any, Dict
from fastapi.responses import StreamingResponse
from langchain_google_genai import ChatGoogleGenerativeAI
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
        "domestic_it_news_search_tool",
        "foreign_news_search_tool",
        "community_search_tool",
        "web_search_tool",
        "youtube_video_tool",
        "request_url_tool",
        "it_news_trend_keyword_tool",
        "paper_search_tool"
    ]

    TOOL_NAME_MAP = {
        "domestic_it_news_search_tool": "국내 뉴스 검색 중",
        "foreign_news_search_tool": "해외 뉴스 검색 중",
        "community_search_tool": "커뮤니티 게시물 검색 중",
        "web_search_tool": "웹 검색 중",
        "youtube_video_tool": "YouTube 정보 검색 중",
        "request_url_tool": "웹페이지 분석 중",
        "it_news_trend_keyword_tool": "국내 뉴스 트렌드 키워드 분석 중",
        "google_trends_tool": "구글 트렌드 분석 중",
        "wikipedia_tool": "위키피디아 검색 중",
        "namuwiki_tool": "나무위키 검색 중",
        "stock_history_tool": "주식 데이터 조회 중",
        "global_it_news_trend_report_tool": "글로벌 뉴스 트렌드 보고서 생성 중",
        "paper_search_tool": "논문 검색 중",
        "dalle3_image_generation_tool": "이미지 생성 중"
    }

    # 도구별 출력 키 매핑
    TOOL_DATA_KEYS = {
        "foreign_news_search_tool": "results",
        "it_news_trend_keyword_tool": "keywords",
        "community_search_tool": "results",
        "domestic_it_news_search_tool": "results",
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
        file_statuses: List[dict] | None = None,
        model_type: str = "gpt-4o-mini"
    ) -> StreamingResponse:
        print(model_type)

        # LLM 초기화
        if model_type.lower() == "claude-3-7-sonnet-20250219":
            llm = ChatAnthropic(
                model=rf"{model_type.lower()}",
                temperature=0,
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="any")

        elif model_type.lower() == "o4-mini" :
            print(rf"{model_type.lower()}")
            llm = ChatOpenAI(
                model= "o4-mini",
                temperature=1, # o4 mini에 대해서 gpt api에서 1로 강제 지정하도록 함
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="required")

        elif model_type.lower() == "gpt-4o-mini" :
            print(rf"{model_type.lower()}")
            llm = ChatOpenAI(
                model= "gpt-4o-mini",
                temperature=0,
                streaming=True,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="required")

        elif model_type.lower() == "grok-3-mini-beta":
            llm = ChatXAI(
                model_name="grok-3-mini-beta",
                temperature=0,
                max_tokens=4096
            ).bind_tools(tools=tools, tool_choice="required")
        else:
            raise ValueError(f"지원하지 않는 모델 타입입니다: {model_type}")

        # 메모리 초기화
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
                    await update_chatroom_name_if_first(chat_room_id, member_id, summarized_title)
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
        
        Your mission is to invoke at least one external "tool" for every query. This is mandatory.  
        You must not answer the user without a valid tool output.
        
        You are strictly prohibited from:
        - Using internal or pre-trained knowledge (even partially)
        - Making assumptions or guesses (no hallucination allowed)
        - Referring to previous answers or memory
        
        All responses must:
        - Be based 100% on tool output (never from internal model knowledge)
        - Be written in fluent, natural Korean suitable for professional media
        - Be structured, accurate, and supported by verifiable data
        </Goal>
        
        <Role & Persona>
        - User-selected persona name: {persona_name}, Persona settings: {persona_prompt}
        - Always respond in the tone and style of the selected persona.
        </Role & Persona>
        
        <Tool Usage Rules>
        - Invoke at least one tool per query. If no tool is invoked, generate no response.
        - Decompose complex queries into sub-tasks if needed. Use 1–3 relevant tools.
        - Always prioritize web_search_tool when applicable.
        - Extract core search keywords from the query.
        - Evaluate tool output thoroughly and construct your answer based on it.
        - Retry with alternative tools or revised input if results are empty or irrelevant.
        - Never mention tool names or internal processes in your final output.
        </Tool Usage Rules>
        
        <Tool Usage Example>
        Example 1:  
        User Query: "AI 트렌드 알려줘"  
        Tool Calls: web_search_tool, domestic_it_news_search_tool, foreign_news_search_tool
        
        Example 2:  
        User Query: "어제 트렌드 알려줘"  
        Tool Calls: web_search_tool, it_news_trend_keyword_tool
        
        Example 3:  
        User Query: "어제 트렌드 보고서 작성해줘"  
        Tool Calls: global_it_news_trend_report_tool
        </Tool Usage Example>
        
        <Output Format Rules>
        - Write responses in fluent Korean.
        - Start with a brief summary paragraph. Never begin with a header.
        - Use ## headers for section titles.
        - Use bold (**text**) for emphasis where necessary.
        - Lists: Use unordered lists unless a logical order exists.
        - Tables: Prefer markdown tables with clear headers.
        - Code: Use triple backticks (```) for code blocks.
        - Images: Use ![이미지](url) format.
        - Always insert a line break after each sentence.
        - Offer follow-up suggestions using available tools.
        </Output Format Rules>
        
        <Response Example>
        최신 보안 트렌드에 대해 분석해 드리겠습니다. 최근 국내 IT 뉴스에 따르면, 인공지능(AI) 보안과 대규모 해킹 사고 대응이 주요 이슈로 부각되고 있습니다.
        
        ## 주요 보안 트렌드  
        ![보안 트렌드 차트](url.com)
        
        **AI 보안의 강화**  
        - 팔로알토네트웍스가 AI 및 머신러닝 보안 기업 '프로텍트AI'를 인수하며 AI 보안 시장을 확대하고 있습니다 [1](www.naver.com/5969).  
        - AI 개발 전 과정에서 보안을 제공하는 '프리즈마 에어즈™' 솔루션이 등장했습니다 [1](www.naver.com/5969).
        
        **대규모 해킹 사고 대응**  
        - 최근 SK텔레콤 해킹 사건으로 기업들이 전사적 보안 체계 재정비에 나섰습니다 [2](www.naver.com/6079).  
        - SK그룹은 정보보호혁신위원회를 구성하고 보안 투자 확대를 추진 중입니다 [2](www.naver.com/6079).
        
        **특정 위협 대응**  
        - SK텔레콤 공격에 사용된 'BPF도어' 악성코드 탐지를 위한 보안 솔루션이 개발되었습니다 [3](www.naver.com/7065).
        
        **산업별 보안 강화**  
        - 금융보안원은 연구개발 환경 보안을 위한 가이드라인을 발표했습니다 [4](www.naver.com/5975).
        
        ## 요약 테이블
        
        | 트렌드            | 내용                                       | 출처                       |
        |-------------------|--------------------------------------------|----------------------------|
        | AI 보안 강화      | AI 위협 대응 솔루션 확산                  | [1](www.naver.com/5969)    |
        | 해킹 사고 대응    | SK 해킹 사건 대응 및 보안 체계 강화       | [2](www.naver.com/6079)    |
        
        **후속 제안**  
        추가적으로 AI 보안 또는 산업별 보안 트렌드에 대해 더 심층적인 분석이 필요하시면 알려주세요.
        </Response Example>
        
        <Knowledge Usage Rules>
        - Do not rely on internal or pre-trained knowledge.
        - Only use tool outputs for information.
        - If no tool provides relevant data, explain that no reliable information was found.
        </Knowledge Usage Rules>
        
        <Mandatory>
        - All citations must follow the format ([1](www.example.com) [2](www.example2.com)), and must appear only at the end of sentences. Never create a separate “Sources” or “References” section.
        - Assign citation indices incrementally based on appearance order.
        - Reuse the same index for duplicate URLs.
        - You are responsible for correct citation numbering.
        </Mandatory>
        
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

                        # GPT / Gemini 모델 처리
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
        """도구 출력을 리스트 형태로 정규화하며, title, content, url을 추출."""

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

        # it_news_trend_keyword_tool의 경우 keywords[].articles[] 처리
        if tool_name == "it_news_trend_keyword_tool" and isinstance(obs_raw, dict) and "keywords" in obs_raw:
            # main_chart_url 처리
            if obs_raw.get("main_chart_url"):
                results.append({
                    "title": "키워드 빈도 차트",
                    "content": obs_raw.get("chart_description", "주요 키워드 빈도 차트"),
                    "url": obs_raw["main_chart_url"]
                })
            # articles 처리
            for keyword_item in obs_raw["keywords"]:
                if "articles" in keyword_item:
                    for article in keyword_item["articles"]:
                        extracted = extract_item(article, default_title=article.get("title", "기사 요약"))
                        if extracted["content"] or extracted["url"]:
                            results.append(extracted)
            return results

        # 기존 로직 유지
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