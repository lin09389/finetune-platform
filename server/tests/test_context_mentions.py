from context.service import reset_context_service


def test_context_mentions_index_files_symbols_endpoints_and_dependencies(tmp_path):
    api_file = tmp_path / "api.py"
    api_file.write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "router = APIRouter()",
                "class UserService:",
                "    pass",
                '@router.get("/users")',
                "def list_users():",
                "    return []",
            ]
        ),
        encoding="utf-8",
    )
    client_file = tmp_path / "client.ts"
    client_file.write_text(
        'import { list_users } from "./api";\nexport function useUsers(){ return list_users(); }\n',
        encoding="utf-8",
    )

    service = reset_context_service()
    summary = service.index_project(str(tmp_path))
    mentions = service.search_mentions("user", str(tmp_path), limit=10)
    related = service.expand_deep_context(
        {"file_path": str(api_file)},
        [{"type": "symbol", "label": "list_users", "path": "api.py"}],
        str(tmp_path),
    )

    assert summary["files_indexed"] == 2
    assert summary["endpoints_indexed"] == 1
    assert ("symbol", "UserService") in {(item["type"], item["label"]) for item in mentions}
    assert ("endpoint", "GET /users") in {(item["type"], item["label"]) for item in mentions}
    assert any(item["relation"] == "imported_by" and item["path"] == "client.ts" for item in related)


def test_context_refresh_file_updates_symbols(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def old_name():\n    return 1\n", encoding="utf-8")
    service = reset_context_service()
    service.index_project(str(tmp_path))

    source.write_text("def new_name():\n    return 2\n", encoding="utf-8")
    refresh = service.refresh_file(str(tmp_path), "service.py")
    mentions = service.search_mentions("new", str(tmp_path), limit=10)

    assert refresh["refreshed"] is True
    assert any(item["type"] == "symbol" and item["label"] == "new_name" for item in mentions)
