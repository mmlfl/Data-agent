"""References are valid only within the current, untruncated model context."""


def clear_schema_context(context):
    context.metadata.pop("known_schema", None)
    context.metadata.pop("schema_searches", None)


def remember_schema(context, version, documents):
    call_id = context.metadata.get("tool_call_id")
    if not call_id:
        return
    known = context.metadata.setdefault("known_schema", {})
    for document in documents:
        if not document.get("columns"):
            continue
        known[document["table_key"].casefold()] = {
            "version": version, "tool_call_id": call_id,
        }


def known_schema(context, version, table_key):
    entry = context.metadata.get("known_schema", {}).get(table_key.casefold())
    visible = context.metadata.get("visible_tool_ids")
    return entry if (entry and entry["version"] == version
                     and (visible is None or entry["tool_call_id"] in visible)) else None
