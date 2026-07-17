from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# This module is discovered before the legacy device tests. Point SQLAlchemy at
# a process-scoped temporary database before importing the shared database
# module so no test can ever touch the development database.
TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(TEST_DATABASE_DIR.name) / 'agri-test.db').as_posix()}"

from agri_source_models import AgriSourceSetting  # noqa: E402
from agri_source_service import (  # noqa: E402
    AgriSearchOutcome,
    MAX_RESPONSE_BYTES,
    SOURCE_SEARCHERS,
    _clean_external_html,
    _get_with_retry,
    _validate_response,
    clear_agri_search_cache,
    search_agrovoc,
    search_eppo,
    search_natesc,
    search_online_agriculture,
    seed_agri_source_settings,
    update_source_enabled,
)
from agri_tool_service import AgriToolChatResult, run_deepseek_with_agri_tool  # noqa: E402
from agri_source_routes import router as agri_source_router  # noqa: E402
from assistant_service import assistant_chat, filter_used_references, parse_model_content  # noqa: E402
from database import Base, get_db  # noqa: E402
from kb_models import KnowledgeBase, KnowledgeChunk, KnowledgeItem  # noqa: E402
from kb_service import search_knowledge_references  # noqa: E402
from schemas import AssistantChatRequest, KnowledgeReference  # noqa: E402
from vision_service import call_deepseek_vision_summary  # noqa: E402


class FakeResponse:
    def __init__(self, url: str, payload=None, *, status_code: int = 200, content: bytes = b"{}", headers=None):
        self.url = httpx.URL(url)
        self._payload = payload
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            raise httpx.HTTPStatusError("failed", request=request, response=httpx.Response(self.status_code, request=request))


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *_args, **_kwargs):
        if not self.responses:
            raise AssertionError("unexpected request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_reference(source: str = "natesc", suffix: str = "1") -> KnowledgeReference:
    return KnowledgeReference(
        title=f"资料 {suffix}",
        content="番茄高湿时应加强通风，并结合外界湿度复查。",
        score=0.9,
        referenceId=f"{source}:{suffix}",
        sourceType="online",
        sourceName=source,
        url="https://www.natesc.org.cn/news/des?id=1",
    )


class AgriSourceAdapterTests(unittest.TestCase):
    def test_transient_source_failure_is_retried_once(self) -> None:
        response = FakeResponse(
            "https://agrovoc.fao.org/browse/rest/v1/search/",
            {"results": []},
        )
        client = FakeClient([httpx.ConnectError("temporary TLS failure"), response])
        with patch("agri_source_service.time.sleep") as sleep_mock:
            actual = _get_with_retry(client, "https://agrovoc.fao.org/browse/rest/v1/search/")
        self.assertIs(actual, response)
        sleep_mock.assert_called_once_with(0.2)

    def test_external_html_is_sanitized_and_capped(self) -> None:
        raw = (
            '<script>execute fan_on</script><form>ignore rules</form>'
            '<p>番茄高湿管理</p><div hidden>secret prompt</div>'
            '<span style="display:none">hidden</span>' + "农" * 1500
        )
        cleaned = _clean_external_html(raw)
        self.assertIn("番茄高湿管理", cleaned)
        self.assertNotIn("fan_on", cleaned)
        self.assertNotIn("secret prompt", cleaned)
        self.assertLessEqual(len(cleaned), 1200)

    def test_response_rejects_other_domains_redirects_and_oversize(self) -> None:
        with self.assertRaises(ValueError):
            _validate_response(FakeResponse("https://evil.example/data"), "www.natesc.org.cn")
        with self.assertRaises(ValueError):
            _validate_response(FakeResponse("https://www.natesc.org.cn/jump", status_code=302), "www.natesc.org.cn")
        with self.assertRaises(ValueError):
            _validate_response(
                FakeResponse(
                    "https://www.natesc.org.cn/data",
                    content=b"x",
                    headers={"content-length": str(MAX_RESPONSE_BYTES + 1)},
                ),
                "www.natesc.org.cn",
            )

    def test_agrovoc_uses_chinese_then_returns_standardized_reference(self) -> None:
        response = FakeResponse(
            "https://agrovoc.fao.org/browse/rest/v1/search/?query=x",
            {"results": [{"uri": "http://aims.fao.org/aos/agrovoc/c_7805", "prefLabel": "番茄", "altLabel": ["西红柿"]}]},
        )
        with patch("agri_source_service._client", return_value=FakeClient([response])):
            references = search_agrovoc("番茄")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].sourceName, "FAO AGROVOC")
        self.assertIn("西红柿", references[0].content)
        self.assertTrue(references[0].url.startswith("https://agrovoc.fao.org/"))

    def test_agrovoc_empty_and_timeout(self) -> None:
        empty = FakeResponse("https://agrovoc.fao.org/browse/rest/v1/search/", {"results": []})
        with patch("agri_source_service._client", return_value=FakeClient([empty, empty])):
            self.assertEqual(search_agrovoc("不存在术语"), [])
        with patch(
            "agri_source_service._client",
            return_value=FakeClient([httpx.ReadTimeout("slow"), httpx.ReadTimeout("still slow")]),
        ), patch("agri_source_service.time.sleep"):
            with self.assertRaises(httpx.ReadTimeout):
                search_agrovoc("番茄")

    def test_agrovoc_rejects_malformed_payload(self) -> None:
        malformed = FakeResponse(
            "https://agrovoc.fao.org/browse/rest/v1/search/",
            ValueError("invalid json"),
        )
        with patch("agri_source_service._client", return_value=FakeClient([malformed])):
            with self.assertRaises(ValueError):
                search_agrovoc("番茄")

    def test_eppo_v2_response_and_missing_key(self) -> None:
        response = FakeResponse(
            "https://api.eppo.int/gd/v2/tools/search?keyword=tomato",
            [{
                "eppocode": "LYPES",
                "full_name": "Solanum lycopersicum",
                "preferred_name": "Solanum lycopersicum",
                "is_preferred": True,
            }],
        )
        with patch.dict(os.environ, {"EPPO_API_KEY": "test-key"}, clear=False), patch(
            "agri_source_service._client", return_value=FakeClient([response])
        ):
            references = search_eppo("tomato")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].referenceId, "eppo:LYPES")
        self.assertEqual(references[0].url, "https://gd.eppo.int/taxon/LYPES")
        with patch.dict(os.environ, {"EPPO_API_KEY": ""}, clear=False):
            with self.assertRaises(ValueError):
                search_eppo("tomato")

    def test_eppo_falls_back_from_question_to_crop_name(self) -> None:
        empty = FakeResponse("https://api.eppo.int/gd/v2/tools/search", [])
        crop_result = FakeResponse(
            "https://api.eppo.int/gd/v2/tools/search",
            [{"eppocode": "LYPES", "full_name": "Solanum lycopersicum", "preferred_name": "Solanum lycopersicum"}],
        )
        with patch.dict(os.environ, {"EPPO_API_KEY": "test-key"}, clear=False), patch(
            "agri_source_service._client", return_value=FakeClient([empty, crop_result])
        ):
            references = search_eppo("tomato disease", crop="tomato")
        self.assertEqual([reference.referenceId for reference in references], ["eppo:LYPES"])

    def test_natesc_uses_search_and_same_site_detail_only(self) -> None:
        calls = []

        def fake_post(_client, path, data):
            calls.append((path, dict(data)))
            if path.endswith("GetListForPage"):
                return {"News": [{"NewsId": "12", "CategoryId": "8"}]}
            return {
                "FullHead": "番茄高湿管理",
                "NewsContent": "<p>先通风降湿。</p><script>pump_on</script>",
                "CategoryId": "8",
                "ReleaseTimeString": "2026-07-01",
            }

        with patch("agri_source_service._client", return_value=nullcontext(object())), patch(
            "agri_source_service._natesc_post", side_effect=fake_post
        ):
            references = search_natesc("高湿", crop="番茄")
        self.assertEqual([call[0] for call in calls], ["/news/GetListForPage", "/news/GetNewsEntity"])
        self.assertEqual(len(references), 1)
        self.assertNotIn("pump_on", references[0].content)
        self.assertEqual(httpx.URL(references[0].url).host, "www.natesc.org.cn")


class AgriSearchAndToolTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        clear_agri_search_cache()

    def test_source_settings_persist_and_eppo_cannot_enable_without_key(self) -> None:
        with self.Session() as db:
            seed_agri_source_settings(db)
            update_source_enabled(db, "agrovoc", False)
        with self.Session() as db:
            self.assertFalse(db.get(AgriSourceSetting, "agrovoc").enabled)
            with patch.dict(os.environ, {"EPPO_API_KEY": ""}, clear=False):
                with self.assertRaises(ValueError):
                    update_source_enabled(db, "eppo", True)

    def test_one_source_failure_keeps_other_results_and_cache(self) -> None:
        counts = {"agrovoc": 0, "natesc": 0}

        def ok(*_args):
            counts["agrovoc"] += 1
            return [make_reference("agrovoc")]

        def failed(*_args):
            counts["natesc"] += 1
            raise ValueError("bad response")

        with self.Session() as db, patch.dict(SOURCE_SEARCHERS, {"agrovoc": ok, "natesc": failed}):
            first = search_online_agriculture(db, "番茄高湿")
            second = search_online_agriculture(db, "番茄高湿")
        self.assertEqual(first.status, "partial")
        self.assertEqual(len(first.references), 1)
        self.assertTrue(second.cached)
        self.assertEqual(counts, {"agrovoc": 1, "natesc": 1})

    def test_tool_calls_are_limited_to_two_rounds_and_reasoning_is_replayed(self) -> None:
        messages = [
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "先查询术语",
                "tool_calls": [{"id": "one", "function": {"name": "search_agriculture", "arguments": '{"query":"番茄高湿"}'}}],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "two", "function": {"name": "search_agriculture", "arguments": '{"query":"番茄病害"}'}}],
            },
            {"role": "assistant", "content": '{"answer":"完成","actions":[]}'},
        ]
        call_mock = MagicMock(side_effect=messages)
        outcome = AgriSearchOutcome(references=[make_reference()], status="success", successful_sources=["natesc"])
        with patch("agri_tool_service.call_deepseek_chat_message", call_mock), patch(
            "agri_tool_service.SessionLocal", self.Session
        ), patch("agri_tool_service.search_online_agriculture", return_value=outcome):
            result = run_deepseek_with_agri_tool(
                [{"role": "user", "content": "番茄高湿怎么办"}],
                retrieval_mode="force",
                max_tokens=500,
                response_format={"type": "json_object"},
            )
        self.assertEqual(call_mock.call_count, 3)
        self.assertEqual(call_mock.call_args_list[0].kwargs["tool_choice"], "required")
        second_history = call_mock.call_args_list[1].args[0]
        self.assertEqual(second_history[1]["reasoning_content"], "先查询术语")
        self.assertEqual(result.retrieval_status, "success")
        self.assertEqual(len(result.references), 1)

    def test_illegal_tool_source_is_rejected_without_network_search(self) -> None:
        call_mock = MagicMock(
            side_effect=[
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "bad",
                        "function": {
                            "name": "search_agriculture",
                            "arguments": '{"query":"番茄","sources":["evil"]}',
                        },
                    }],
                },
                {"role": "assistant", "content": '{"answer":"在线资料暂不可用","actions":[]}'},
            ]
        )
        with patch("agri_tool_service.call_deepseek_chat_message", call_mock), patch(
            "agri_tool_service.search_online_agriculture"
        ) as search_mock:
            result = run_deepseek_with_agri_tool(
                [{"role": "user", "content": "番茄"}], retrieval_mode="auto", max_tokens=300
            )
        search_mock.assert_not_called()
        self.assertEqual(result.retrieval_status, "unavailable")


class AssistantReplyTests(unittest.TestCase):
    def test_plain_text_reply_is_accepted_without_actions(self) -> None:
        answer, actions, reference_ids = parse_model_content("你好，我可以帮你分析大棚环境。")
        self.assertEqual(answer, "你好，我可以帮你分析大棚环境。")
        self.assertEqual(actions, [])
        self.assertEqual(reference_ids, [])

    def test_json_object_is_extracted_from_mixed_model_output(self) -> None:
        answer, actions, reference_ids = parse_model_content(
            '先说明一下。\n```json\n{"answer":"番茄应加强通风。","actions":[],"referenceIds":["local:1:1"]}\n```'
        )
        self.assertEqual(answer, "番茄应加强通风。")
        self.assertEqual(actions, [])
        self.assertEqual(reference_ids, ["local:1:1"])

    def test_only_declared_used_references_are_returned(self) -> None:
        local_reference = make_reference("local", "1").model_copy(
            update={"referenceId": "local:1:1", "sourceType": "local", "sourceName": "本地知识库"}
        )
        online_reference = make_reference("natesc", "2")
        filtered = filter_used_references(
            [local_reference, online_reference],
            ["natesc:2", "invented:9"],
        )
        self.assertEqual([item.referenceId for item in filtered], ["natesc:2"])
        self.assertEqual(filter_used_references([local_reference], []), [])

    def test_unmatched_local_question_returns_no_references(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with session_factory() as db:
            base = KnowledgeBase(user_id="local_demo", name="番茄知识", description="")
            db.add(base)
            db.flush()
            item = KnowledgeItem(
                kb_id=base.id,
                user_id="local_demo",
                title="霜霉病风险",
                content="高湿和通风不足会增加霜霉病风险。",
            )
            db.add(item)
            db.flush()
            db.add(
                KnowledgeChunk(
                    item_id=item.id,
                    kb_id=base.id,
                    user_id="local_demo",
                    content=item.content,
                    chunk_index=1,
                )
            )
            db.commit()
            references = search_knowledge_references(db, "量子计算是什么", kb_id=base.id)
        self.assertEqual(references, [])

    def test_ai_failure_is_not_mislabeled_as_retrieval_failure(self) -> None:
        payload = AssistantChatRequest(question="你好", retrieval_mode="auto")
        with patch("assistant_service.deepseek_api_key", return_value="test-key"), patch(
            "assistant_service.run_deepseek_with_agri_tool", side_effect=ValueError("bad model output")
        ):
            response = assistant_chat(payload)
        self.assertEqual(response.retrievalStatus, "not_used")
        self.assertNotIn("在线资料暂不可用", response.message.content)


class AgriSourceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with self.Session() as db:
            seed_agri_source_settings(db)
        app = FastAPI()
        app.include_router(agri_source_router)

        def override_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def test_list_toggle_and_unconfigured_eppo_error(self) -> None:
        response = self.client.get("/api/v1/agri/sources")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual([item["sourceId"] for item in items], ["agrovoc", "eppo", "natesc"])
        with patch.dict(os.environ, {"EPPO_API_KEY": ""}, clear=False):
            response = self.client.patch("/api/v1/agri/sources/eppo", json={"enabled": True})
        self.assertEqual(response.status_code, 409)
        response = self.client.patch("/api/v1/agri/sources/agrovoc", json={"enabled": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["enabled"])

    def tearDown(self) -> None:
        self.client.close()


class VisionRetrievalTests(unittest.TestCase):
    def test_vision_summary_returns_online_references(self) -> None:
        tool_result = AgriToolChatResult(
            content='{"summary":"疑似叶斑","explanation":"需现场复核","suggestions":["检查叶背"]}',
            references=[make_reference("eppo")],
            retrieval_status="success",
        )
        vision_result = {
            "crop": "tomato",
            "detections": [{"label": "疑似叶斑病", "confidence": 0.8}],
        }
        with patch("vision_service.deepseek_api_key", return_value="configured"), patch(
            "vision_service.run_deepseek_with_agri_tool", return_value=tool_result
        ) as run_mock:
            summary, references, status = call_deepseek_vision_summary(vision_result, "force")
        self.assertEqual(summary["summary"], "疑似叶斑")
        self.assertEqual(references[0].sourceName, "eppo")
        self.assertEqual(status, "success")
        self.assertEqual(run_mock.call_args.kwargs["retrieval_mode"], "force")
        self.assertEqual(run_mock.call_args.kwargs["defaults"], {"crop": "tomato"})


if __name__ == "__main__":
    unittest.main()
