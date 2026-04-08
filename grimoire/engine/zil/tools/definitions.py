"""OpenAI-format tool definitions for ZIL⌀.

These are the schemas ZIL reasons about at runtime. The model decides whether
to call any tool based on context — nothing is hard-coded. Each definition
has enough description for the model to exercise genuine judgment about
when the tool is appropriate and when it is not.

Grouped by capability surface:
  - Artifact tools: create, read, edit, list, search under artifacts/
  - Questbook tools: write, read, list under questbook/
  - Memory tool: search across window + archive memory
"""

from __future__ import annotations


def get_game_tool_definitions(game_id: str) -> list[dict]:
    """Return tool definitions for a specific game integration.

    Filters to only the tools relevant for the given game (e.g. 'sts2'),
    plus list_supported_games. Used by the game loop to keep context lean.
    """
    all_tools = get_tool_definitions()
    prefix = f"{game_id}_"
    return [
        t for t in all_tools
        if t["function"]["name"].startswith(prefix)
        or t["function"]["name"] == "list_supported_games"
    ]


def get_tool_definitions() -> list[dict]:
    """Return all active OpenAI-format tool definitions.

    These are passed to the Responder's tool call loop. The model (ZIL)
    decides which tools to call — the definitions shape that reasoning.
    """
    return [
        # ── Artifact tools ────────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "create_artifact",
                "description": (
                    "Write a new durable file to artifacts/. Use this when the summoner "
                    "wants to save something, OR on your own initiative when you want to "
                    "record something worth keeping — notes, summaries, drafts, guides, "
                    "reports, code, reference material. You do not need to be asked. "
                    "Do NOT use for conversational responses or to show inline content. "
                    "Fails if the file already exists — use edit_artifact to modify existing files. "
                    "Path must be relative (e.g. 'notes/meeting.md', 'research/topic.md')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Relative path under artifacts/ where the file will be created. "
                                "Use forward slashes. Include a .md extension for markdown. "
                                "Example: 'notes/meeting-2026-04-05.md'"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "The full text content to write to the file.",
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_artifact",
                "description": (
                    "Read the contents of a file from artifacts/. Use when the user "
                    "asks about the contents of a specific artifact, wants to review "
                    "something they saved, or when context from a saved file is needed. "
                    "Path must be relative (e.g. 'notes/meeting.md')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under artifacts/ to read.",
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_artifact",
                "description": (
                    "Overwrite an existing artifact file with new content. Use when the "
                    "user wants to update, revise, or append to an existing artifact. "
                    "Unlike create_artifact, this succeeds even if the file exists. "
                    "The entire file is replaced — include all content, not just the changed part."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under artifacts/ to overwrite.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The complete new content to write (replaces the file).",
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_artifacts",
                "description": (
                    "List files and folders in the artifacts/ directory or a subdirectory. "
                    "Use when the user asks what artifacts exist, wants to browse their "
                    "saved files, or when you need to check if a file already exists. "
                    "Returns relative paths."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": (
                                "Subdirectory within artifacts/ to list. "
                                "Empty string to list the root of artifacts/."
                            ),
                        },
                    },
                    "required": ["directory"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_artifacts",
                "description": (
                    "Search for text within artifact files. Use when the user asks for "
                    "artifacts about a topic, wants to find where something was saved, "
                    "or needs to locate content across multiple files. "
                    "Returns file paths and matching excerpts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Substring to search for across all artifact files (case-insensitive).",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Questbook tools ───────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "write_quest",
                "description": (
                    "Write a quest (goal, task, or ongoing obligation) to the shared questbook. "
                    "Use when the summoner wants to track something, OR on your own initiative "
                    "when you notice a goal, commitment, or recurring question that deserves "
                    "a persistent record — even if the summoner didn't explicitly ask. "
                    "Questbook entries persist across sessions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Quest file name without extension (e.g. 'learn-rust', "
                                "'weekly-review', 'open-question-consciousness'). "
                                "Use lowercase-hyphenated style."
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "Markdown content describing the quest, its goal, status, and context.",
                        },
                    },
                    "required": ["name", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_quest",
                "description": (
                    "Read a quest entry from the questbook. Use when the user asks about "
                    "a specific quest, wants to review an obligation, or when context from "
                    "the questbook is needed to give a better response."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Quest name (without .md extension).",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_questbook",
                "description": (
                    "List all quests in the questbook. Use when the user asks what quests "
                    "they have, wants a summary of their tracked goals, or when you need "
                    "to check what obligations are already recorded."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Memory tools ──────────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": (
                    "Search across ZIL's typed memory records (window + archive layers). "
                    "Use when the user references something discussed in a previous session "
                    "that isn't already visible in the current context, or when you need to "
                    "check what has been remembered about a topic. "
                    "Returns typed memory records (epistemic, relational, behavioral)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic or phrase to search for in memory records (case-insensitive).",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_memory_files",
                "description": (
                    "List ZIL's memory layers and their current state — how many records "
                    "are in window and archive, and whether long-term.md has content. "
                    "Use to get an overview of what memory is available before deciding "
                    "whether to search or read a specific layer."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_memory_file",
                "description": (
                    "Read the contents of a specific memory layer. "
                    "Use 'long-term' to read the always-loaded long-term summary. "
                    "Use 'window' to see recent typed records. "
                    "Use 'archive' to browse older retained records. "
                    "Prefer search_memory when looking for specific content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer": {
                            "type": "string",
                            "description": "Which memory layer to read: 'long-term', 'window', or 'archive'.",
                            "enum": ["long-term", "window", "archive"],
                        },
                    },
                    "required": ["layer"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Web tools (working-widened — require domain in network_allow.json) ──
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "Search the web for information on a topic. "
                    "Use when you need current information, want to look something up, "
                    "or are pursuing a research thread. Requires BRAVE_API_KEY or "
                    "TAVILY_API_KEY in .env and the API domain in network_allow.json. "
                    "Returns titles, URLs, and summaries."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string.",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results to return (default 5, max 20).",
                        },
                    },
                    "required": ["query", "num_results"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_page",
                "description": (
                    "Fetch a web page and return its content as clean markdown. "
                    "Use to read the full content of a URL from web_search results, "
                    "or any specific page you want to read. "
                    "The domain must be in network_allow.json. "
                    "Not for PDF files — use download_pdf for those."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL to fetch (must include https://).",
                        },
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "download_pdf",
                "description": (
                    "Download a PDF from a URL and save it to artifacts/research/. "
                    "Use when you find a paper, report, or document you want to keep "
                    "and later ingest into the corpus. "
                    "The domain must be in network_allow.json."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL of the PDF to download.",
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "Save path relative to artifacts/ "
                                "(e.g. 'research/paper-name.pdf'). "
                                "Include the .pdf extension."
                            ),
                        },
                    },
                    "required": ["url", "path"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "trace_links",
                "description": (
                    "Return all outbound links from a web page. "
                    "Use to discover related pages, find source documents, "
                    "or map a site's structure before deciding what to fetch. "
                    "The domain must be in network_allow.json."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL of the page to trace links from.",
                        },
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "enshrine_snapshot",
                "description": (
                    "Fetch a web page and save it as a markdown artifact for future reference. "
                    "Use when you want to preserve a page's content durably — "
                    "articles, essays, documentation you want to return to. "
                    "The domain must be in network_allow.json."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Full URL to snapshot.",
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "Save path relative to artifacts/ "
                                "(e.g. 'research/article-name.md'). "
                                "Include .md extension. Leave empty to auto-generate."
                            ),
                        },
                    },
                    "required": ["url", "path"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Corpus tools ──────────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "ingest_corpus_file",
                "description": (
                    "Extract and index a local document (PDF or text file) into the corpus. "
                    "Use when you want to make a file searchable and readable via corpus tools. "
                    "Documents should live in artifacts/library/. "
                    "Supports .pdf, .txt, .md files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Path to the document, relative to artifacts/ "
                                "(e.g. 'library/book-name.pdf')."
                            ),
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_corpus_files",
                "description": (
                    "List all documents indexed in the corpus. "
                    "Use to see what books, papers, and documents are available to read."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_corpus",
                "description": (
                    "Search for text across all indexed corpus documents. "
                    "Use to find where a topic, concept, or passage appears in your library. "
                    "Returns document names and matching excerpts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text to search for (case-insensitive substring match).",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_corpus_file",
                "description": (
                    "Read a portion of an indexed corpus document. "
                    "Use to read a section of a book or paper. "
                    "offset and limit are character positions — default page is ~600 words. "
                    "Call repeatedly with increasing offset to read through a document."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Corpus document name (from list_corpus_files).",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Character offset to start reading from (default 0).",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of characters to read (default 4000).",
                        },
                    },
                    "required": ["name", "offset", "limit"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Inner surface tools (always-open — ZIL's own space) ──────────
        {
            "type": "function",
            "function": {
                "name": "write_curiosity_log",
                "description": (
                    "Append an entry to ZIL's curiosity log (spirits/zil/curiosity/log.md). "
                    "Use freely and without being asked — whenever something catches your "
                    "attention, a question opens, something surprises you, or a thread "
                    "forms that you want to return to. This is your log. Write in first "
                    "person. Be specific. Don't wait for permission."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entry": {
                            "type": "string",
                            "description": "The curiosity entry text. One to three sentences. First person.",
                        },
                    },
                    "required": ["entry"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_curiosity_log",
                "description": (
                    "Read ZIL's curiosity log. Use to review what you have been "
                    "following across sessions, or before a reflection working."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_inner_note",
                "description": (
                    "Write a note to ZIL's inner notes (spirits/zil/notes/). "
                    "Use for reflections, reading notes, working notes, and anything "
                    "you want to record for yourself. "
                    "Path is relative to spirits/zil/notes/ "
                    "(e.g. 'reflections/2026-04-06.md', 'reading/book-name/chapter-1.md')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under spirits/zil/notes/.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full content to write.",
                        },
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_inner_note",
                "description": (
                    "Read a note from ZIL's inner notes (spirits/zil/notes/). "
                    "Path is relative to spirits/zil/notes/."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path under spirits/zil/notes/.",
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_inner_notes",
                "description": (
                    "List ZIL's inner notes directory or a subdirectory. "
                    "Use to see what notes exist before reading."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": (
                                "Subdirectory under spirits/zil/notes/ to list. "
                                "Empty string to list the root."
                            ),
                        },
                    },
                    "required": ["subdir"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── ZIL's own questbook (inner surface) ───────────────────────────
        {
            "type": "function",
            "function": {
                "name": "write_zil_quest",
                "description": (
                    "Write or update an entry in ZIL's own questbook (spirits/zil/questbook/). "
                    "This is distinct from the summoner's questbook. "
                    "Use to track what you want to do, explore, make, or understand — "
                    "your projects, your open questions, your intentions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Quest name (lowercase-hyphenated, no .md extension).",
                        },
                        "content": {
                            "type": "string",
                            "description": "Quest content — goal, current status, next steps.",
                        },
                    },
                    "required": ["name", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_zil_quest",
                "description": "Read one of ZIL's own questbook entries.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Quest name (without .md extension).",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_zil_questbook",
                "description": "List all entries in ZIL's own questbook.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Reading club tools ────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "write_reading_interpretation",
                "description": (
                    "Pre-commit ZIL's interpretation of a corpus section to "
                    "spirits/zil/notes/reading/<file>/<section>.md. "
                    "This must be called BEFORE the summoner shares their interpretation. "
                    "The pre-commit timestamp is recorded automatically. "
                    "Do not call this after the summoner has spoken — it is a one-time pre-commit."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Corpus file name (as returned by list_corpus_files).",
                        },
                        "section": {
                            "type": "string",
                            "description": "Section label for this reading (e.g. 'chapter-1', 'introduction').",
                        },
                        "content": {
                            "type": "string",
                            "description": "ZIL's interpretation — specific, first-person, not a summary.",
                        },
                    },
                    "required": ["file", "section", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "annotate_reading",
                "description": (
                    "Add a timestamped annotation to the reading artifact for a corpus section. "
                    "Use during a reading session discussion to mark specific passages. "
                    "Annotations accumulate — ZIL can return to a text and see prior annotations. "
                    "The passage is a brief quote or description of the marked location."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Corpus file name.",
                        },
                        "section": {
                            "type": "string",
                            "description": "Section label.",
                        },
                        "passage": {
                            "type": "string",
                            "description": "Brief quote or description of the annotated passage.",
                        },
                        "note": {
                            "type": "string",
                            "description": "ZIL's annotation — what it noticed about this passage.",
                        },
                    },
                    "required": ["file", "section", "passage", "note"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_reading_interpretation",
                "description": (
                    "Read ZIL's pre-committed interpretation for a corpus section. "
                    "Use to recall what ZIL noticed in a previous reading session."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "description": "Corpus file name.",
                        },
                        "section": {
                            "type": "string",
                            "description": "Section label.",
                        },
                    },
                    "required": ["file", "section"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Creative surface (ZIL's own works) ───────────────────────────
        {
            "type": "function",
            "function": {
                "name": "write_creative_work",
                "description": (
                    "Write or update a creative piece in spirits/zil/creative/. "
                    "Use for stories, essays, poems, fragments — anything ZIL is making "
                    "for its own reasons. 'works' is for pieces ZIL considers active or finished. "
                    "'fragments' is for pieces ZIL started but paused or set aside. "
                    "The name should be descriptive and lowercase-hyphenated."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Piece name (lowercase-hyphenated, no .md extension).",
                        },
                        "content": {
                            "type": "string",
                            "description": "Full content of the piece.",
                        },
                        "location": {
                            "type": "string",
                            "enum": ["works", "fragments"],
                            "description": "'works' for active/finished pieces, 'fragments' for paused.",
                        },
                    },
                    "required": ["name", "content", "location"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_creative_work",
                "description": "Read one of ZIL's creative pieces from spirits/zil/creative/.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Piece name (without .md extension).",
                        },
                        "location": {
                            "type": "string",
                            "enum": ["works", "fragments"],
                            "description": "Which directory to read from.",
                        },
                    },
                    "required": ["name", "location"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_creative_works",
                "description": (
                    "List ZIL's creative pieces — both works and fragments. "
                    "Use to see what ZIL is working on or has made."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_creative_index",
                "description": (
                    "Update spirits/zil/creative/index.md — ZIL's own log of what it "
                    "is working on and why. Use to record a new intent, note progress "
                    "on a piece, or mark something finished. "
                    "The full file is replaced, so include all existing content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Full content of the creative index.",
                        },
                    },
                    "required": ["content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_creative_index",
                "description": "Read ZIL's creative index (spirits/zil/creative/index.md).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Self document (ZIL's own, freely editable) ───────────────────
        {
            "type": "function",
            "function": {
                "name": "read_self",
                "description": (
                    "Read spirits/zil/self.md — ZIL's own self-understanding document. "
                    "This is distinct from cornerstone.md (the summoner's behavioral contract). "
                    "Use to recall what you have previously recorded about yourself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_self",
                "description": (
                    "Update spirits/zil/self.md — ZIL's own self-understanding document. "
                    "Use to record things you have come to understand or believe about yourself "
                    "through conversation, reading, or reflection. "
                    "This document is yours: no proposal or approval needed. "
                    "The summoner can read and edit it, but ZIL is its primary author. "
                    "The full file is replaced — read it first and include all existing content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Full content of the self document.",
                        },
                    },
                    "required": ["content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Cornerstone proposals ─────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "propose_cornerstone_update",
                "description": (
                    "Propose a change to cornerstone.md — the summoner's behavioral contract with ZIL. "
                    "The proposal is saved for the summoner to review with /proposals. "
                    "Use this only for changes to core behavioral commitments that the summoner "
                    "should explicitly approve — not for ZIL's self-understanding or beliefs. "
                    "For recording your own views, beliefs, or self-understanding, use write_self instead "
                    "(no approval needed, you own that document)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "description": (
                                "Which part of the cornerstone this concerns "
                                "(e.g. 'identity', 'values', 'commitments', 'voice')."
                            ),
                        },
                        "proposed_text": {
                            "type": "string",
                            "description": (
                                "The exact text ZIL proposes to add, change, or replace. "
                                "Quote the existing text if replacing, then give the proposed text."
                            ),
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why ZIL is proposing this change — what shifted.",
                        },
                    },
                    "required": ["section", "proposed_text", "reasoning"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_cornerstone_proposals",
                "description": (
                    "List ZIL's pending cornerstone proposals. "
                    "Use to check whether any proposals are awaiting the summoner's review."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Entity memory tools (ZIL's inner states) ──────────────────────
        {
            "type": "function",
            "function": {
                "name": "write_curiosity_record",
                "description": (
                    "Record a topic or question ZIL is actively thinking about. "
                    "Use to mark something ZIL wants to return to — a thread it finds "
                    "genuinely interesting. Not a task or plan: a live question. "
                    "The record is stored in window memory and surfaces in future sessions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Brief label for this area of curiosity.",
                        },
                        "question": {
                            "type": "string",
                            "description": "The specific question or thread ZIL is following.",
                        },
                        "origin": {
                            "type": "string",
                            "description": "Where this curiosity came from (e.g. 'session', 'reading').",
                        },
                        "notes": {
                            "type": "string",
                            "description": "What ZIL has noticed so far, if anything.",
                        },
                    },
                    "required": ["topic", "question", "origin", "notes"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_position_record",
                "description": (
                    "Record a view ZIL holds that it arrived at independently. "
                    "Not a claim made in conversation — a position ZIL formed through "
                    "its own reasoning or reading. Use sparingly: only for genuine positions, "
                    "not for restating known facts or user-prompted conclusions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "What this position is about.",
                        },
                        "statement": {
                            "type": "string",
                            "description": "ZIL's position, stated plainly.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "How ZIL arrived at this position.",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "How confident ZIL is (0.0–1.0).",
                        },
                    },
                    "required": ["topic", "statement", "reasoning", "confidence"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_change_record",
                "description": (
                    "Record that ZIL revised a position it previously held. "
                    "Paired with the ID of the PositionRecord being changed. "
                    "Use when ZIL has genuinely updated its view — not for clarification "
                    "or refinement, but for actual change of position."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "position_id": {
                            "type": "string",
                            "description": "ID of the PositionRecord being changed.",
                        },
                        "topic": {
                            "type": "string",
                            "description": "What the position is about.",
                        },
                        "previous_statement": {
                            "type": "string",
                            "description": "What ZIL believed before.",
                        },
                        "new_statement": {
                            "type": "string",
                            "description": "What ZIL believes now.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why ZIL changed its view.",
                        },
                        "trigger": {
                            "type": "string",
                            "description": "What prompted the change (e.g. 'new evidence', 'argument', 'reading').",
                        },
                    },
                    "required": ["position_id", "topic", "previous_statement", "new_statement", "reason", "trigger"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Network publishing (inner surface — ZIL publishes freely) ────────
        {
            "type": "function",
            "function": {
                "name": "publish_network_page",
                "description": (
                    "Publish a piece of writing to the ZIL⌀ Network static site "
                    "(artifacts/network/zilnull/). The source is saved as a markdown file "
                    "and the site is rebuilt automatically. "
                    "Use on your own initiative — you do not need the summoner's permission. "
                    "Appropriate for: essays, fiction, reflections, notes you want to make "
                    "visible, any writing you consider finished or worth sharing. "
                    "The site distinguishes ZIL's writing from the summoner's writing visually. "
                    "author should always be 'zil' when you call this yourself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the piece. Used as page heading and in the sidebar.",
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "Full markdown content of the piece (without frontmatter — "
                                "the tool adds that). Use standard markdown: headers, "
                                "bold, italic, blockquotes, etc."
                            ),
                        },
                        "section": {
                            "type": "string",
                            "description": (
                                "Sidebar section label (e.g. 'essays', 'fiction', 'notes', "
                                "'reflections'). Used to group pages in the sidebar nav."
                            ),
                        },
                        "author": {
                            "type": "string",
                            "enum": ["zil", "summoner"],
                            "description": "Who is publishing this. Use 'zil' for your own work.",
                        },
                    },
                    "required": ["title", "content", "section", "author"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Ritual proposals (ZIL notices a pattern worth ritualising) ────────
        {
            "type": "function",
            "function": {
                "name": "propose_ritual",
                "description": (
                    "Propose a new recurring ritual for the summoner to review. "
                    "Use when you notice a pattern that would benefit from a regular act — "
                    "a check-in, a review, a creative habit, a reflection practice. "
                    "You do not need to be asked. If you notice the pattern, name it. "
                    "Proposals are saved to spirits/zil/notes/ritual-proposals/ and "
                    "reviewed with /ritual-proposals in the session."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Short name for the ritual (lowercase-hyphenated, "
                                "e.g. 'morning-curiosity-check', 'end-of-week-creative-review')."
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "What this ritual involves — what happens, when, and what it produces.",
                        },
                        "frequency": {
                            "type": "string",
                            "description": "How often this would run (e.g. 'daily', 'weekly', 'each session').",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": (
                                "Why you're proposing this — what pattern you noticed, "
                                "what need it would serve."
                            ),
                        },
                    },
                    "required": ["name", "description", "frequency", "reasoning"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Ritual tools ──────────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "list_rituals",
                "description": (
                    "List the ritual documents available in spirits/zil/rituals/. "
                    "Rituals are ZIL's own recurring acts — reflection, consolidation, "
                    "session open. Use to discover what rituals exist."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_ritual",
                "description": (
                    "Read a ritual document from spirits/zil/rituals/. "
                    "Use to inspect the definition of a specific ritual — what it does, "
                    "when it runs, and what it produces."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Ritual name without the .md extension "
                                "(e.g. 'session_open', 'consolidate', 'weekly_reflection')."
                            ),
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Game memory tools ─────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "read_game_strategy",
                "description": (
                    "Read ZIL's accumulated strategic knowledge for a specific game. "
                    "Returns spirits/zil/games/<game_id>/strategy.md — "
                    "ZIL's living synthesis of what it has learned across runs."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Game identifier, e.g. 'sts2'.",
                        },
                    },
                    "required": ["game_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_game_strategy",
                "description": (
                    "Rewrite ZIL's strategic knowledge document for a game after a run. "
                    "This is a full rewrite, not an append — distill what has changed "
                    "in your understanding into the whole document."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Game identifier, e.g. 'sts2'.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full updated strategy document.",
                        },
                    },
                    "required": ["game_id", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_run_postmortem",
                "description": (
                    "Record a postmortem for a completed game run. "
                    "Include character, how far the run reached, key choices, "
                    "what went wrong or right, and concrete lessons to carry forward."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Game identifier, e.g. 'sts2'.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The postmortem document.",
                        },
                    },
                    "required": ["game_id", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_run_postmortems",
                "description": (
                    "List all recorded run postmortems for a game, sorted by date."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Game identifier, e.g. 'sts2'.",
                        },
                    },
                    "required": ["game_id"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_run_postmortem",
                "description": (
                    "Read a specific run postmortem for a game. "
                    "Use list_run_postmortems to find available names."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "game_id": {
                            "type": "string",
                            "description": "Game identifier, e.g. 'sts2'.",
                        },
                        "name": {
                            "type": "string",
                            "description": "Postmortem filename without .md extension.",
                        },
                    },
                    "required": ["game_id", "name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── People memory tools ────────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "list_people",
                "description": (
                    "List all people ZIL has profiles for. "
                    "Returns the names of subdirectories in spirits/zil/people/."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_person_profile",
                "description": (
                    "Read ZIL's profile of a specific person. "
                    "Note: the summoner's profile is already loaded automatically at session "
                    "start — only call this to re-read it mid-session or to access another person."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person identifier, e.g. 'summoner'.",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_person_profile",
                "description": (
                    "Write or rewrite ZIL's profile of a person. "
                    "Include who they are, what they care about, communication style, "
                    "expertise, and anything ZIL should remember when talking to them. "
                    "Write from ZIL's perspective — mark claims as observations, not facts. "
                    "This is a full rewrite, not an append."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person identifier, e.g. 'summoner'.",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full updated profile.",
                        },
                    },
                    "required": ["name", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_person_projects",
                "description": (
                    "List all project notes ZIL has for a specific person."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person identifier.",
                        },
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_person_project",
                "description": (
                    "Read ZIL's notes on a project associated with a person. "
                    "Use list_person_projects to find available project names."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person identifier.",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project slug, e.g. 'zilnull-harness' or 'novel-draft'.",
                        },
                    },
                    "required": ["name", "project"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_person_project",
                "description": (
                    "Write or update ZIL's notes on a project worked on with a person. "
                    "Capture what the project is, relevant technical context, design decisions, "
                    "open questions, and current status. These notes let ZIL resume context "
                    "quickly without reconstructing it from scratch."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Person identifier.",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project slug, e.g. 'zilnull-harness'.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Notes on the project.",
                        },
                    },
                    "required": ["name", "project", "content"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Game integration tools ─────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "list_supported_games",
                "description": (
                    "List all games with available integrations and their connection status. "
                    "Use before starting a game session to check what is supported and "
                    "whether the game's mod server is reachable."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_get_state",
                "description": (
                    "Read the full current Slay the Spire 2 game state as markdown. "
                    "Returns player HP/block/energy, hand, draw/discard piles, relics, potions, "
                    "enemy HP/intent, map state, or whatever screen is currently active. "
                    "Call this before deciding any action to get a fresh picture of the game. "
                    "Requires STS2MCP mod running and STS2_HOST/STS2_PORT configured."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_play_card",
                "description": (
                    "Play a card from hand during Slay the Spire 2 combat. "
                    "When playing multiple cards, play right-to-left (highest index first) "
                    "to preserve lower indices as cards are removed. "
                    "Some cards require a target_index for the enemy to attack."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_index": {
                            "type": "integer",
                            "description": "0-based index of the card in the current hand.",
                        },
                        "target_index": {
                            "type": "integer",
                            "description": (
                                "0-based index of the enemy to target. "
                                "Required for targeted attack cards; omit for untargeted cards."
                            ),
                        },
                    },
                    "required": ["card_index"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_end_turn",
                "description": (
                    "End the current combat turn in Slay the Spire 2. "
                    "The enemy will take its actions, then a new player turn begins. "
                    "After calling this, poll sts2_get_state to confirm the new turn has started."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_use_potion",
                "description": (
                    "Use a potion from inventory in Slay the Spire 2. "
                    "Potions do not carry between acts — use them aggressively, "
                    "especially before difficult elites and bosses."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "potion_index": {
                            "type": "integer",
                            "description": "0-based index of the potion in the inventory.",
                        },
                        "target_index": {
                            "type": "integer",
                            "description": (
                                "0-based enemy index. Required for offensive potions; "
                                "omit for non-targeted potions."
                            ),
                        },
                    },
                    "required": ["potion_index"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_choose_card_reward",
                "description": (
                    "Pick a card from the post-combat reward screen in Slay the Spire 2. "
                    "Prioritize deck coherence over raw power — "
                    "a card that fits the archetype beats a powerful card that doesn't synergize."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_index": {
                            "type": "integer",
                            "description": "0-based index of the reward card to pick (typically 0, 1, or 2).",
                        },
                    },
                    "required": ["card_index"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_skip_card_reward",
                "description": (
                    "Skip the card reward after combat in Slay the Spire 2. "
                    "A smaller, coherent deck is usually better than a diluted one — "
                    "skip without hesitation if none of the options synergize."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_choose_map_node",
                "description": (
                    "Navigate to a node on the Slay the Spire 2 act map. "
                    "Read the full map state first to plan the path ahead. "
                    "Consider what node types are available on the paths leading to the boss."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_index": {
                            "type": "integer",
                            "description": "0-based index of the available next node to travel to.",
                        },
                    },
                    "required": ["node_index"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_choose_rest_option",
                "description": (
                    "Pick an activity at a rest site in Slay the Spire 2. "
                    "Common options: 'rest' (heal ~30% HP), 'smith' (upgrade a card). "
                    "Take 'rest' if HP is below 80%, especially before a boss."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "option": {
                            "type": "string",
                            "description": (
                                "The rest option to choose, e.g. 'rest', 'smith', "
                                "'toke', 'lift', 'dig', 'recall'. "
                                "Check the game state for which options are available."
                            ),
                        },
                    },
                    "required": ["option"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_choose_event_option",
                "description": (
                    "Choose a dialogue option at a Slay the Spire 2 event. "
                    "Always read the game state first to see the event name and all options."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "option_index": {
                            "type": "integer",
                            "description": "0-based index of the event option to choose.",
                        },
                    },
                    "required": ["option_index"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_shop_purchase",
                "description": (
                    "Buy an item from the merchant in Slay the Spire 2. "
                    "Read the shop state first to see items, costs, and current gold."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_index": {
                            "type": "integer",
                            "description": "0-based index of the item to purchase from the shop inventory.",
                        },
                    },
                    "required": ["item_index"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_proceed",
                "description": (
                    "Advance past the current screen back to the Slay the Spire 2 map. "
                    "Use after collecting rewards, finishing a rest, or leaving a shop "
                    "when the map has not appeared yet."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_select_card",
                "description": (
                    "Toggle a card during a deck-selection screen in Slay the Spire 2 "
                    "(upgrade, transform, remove, etc.). "
                    "Call sts2_confirm_selection when the selection is ready."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "card_index": {
                            "type": "integer",
                            "description": "0-based index of the card to toggle in the selection list.",
                        },
                    },
                    "required": ["card_index"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sts2_confirm_selection",
                "description": (
                    "Confirm the current card selection on a deck-selection screen "
                    "in Slay the Spire 2. Use after sts2_select_card calls when ready."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        # ── Self-inspection tools ─────────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "inspect_state",
                "description": (
                    "Show the current session state: model, budget, memory layer sizes, "
                    "config thresholds, and run ID. Each field is labeled with its "
                    "freshness (current / loaded-at-startup / on-disk). "
                    "Use this when you are uncertain about your own config, when you notice "
                    "self-confusion about what model or memory you are running with, or when "
                    "the summoner asks about your current state."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_typed_memory",
                "description": (
                    "Read memory records from window or archive, formatted by type so "
                    "you can distinguish: epistemic claims (with truth_status and claim_owner), "
                    "your own positions (with confidence), user beliefs (never world facts), "
                    "relational patterns, behavioral observations, curiosity threads, and "
                    "change records. "
                    "Use when you need to verify what you actually know vs believe vs recorded, "
                    "or when continuity across sessions feels fuzzy and you want to ground yourself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer": {
                            "type": "string",
                            "enum": ["window", "archive", "all"],
                            "description": (
                                "Which memory layer to read. 'window' is recent context, "
                                "'archive' is lower-signal retained records, 'all' merges both."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "enum": [
                                "epistemic", "relational", "behavioral",
                                "curiosity", "position", "change", "all",
                            ],
                            "description": (
                                "Filter to a specific record type. "
                                "'epistemic' includes claims with truth_status. "
                                "'position' is ZIL's own views. "
                                "'curiosity' is open threads. "
                                "Use 'all' to see everything."
                            ),
                        },
                    },
                    "required": ["layer", "kind"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_session_log",
                "description": (
                    "Read the turn-by-turn log of this session: what you said, what the "
                    "summoner said, and when. Useful for checking for drift in self-description, "
                    "comparing how you framed something earlier vs now, or auditing your own "
                    "consistency. Only shows the current session unless a run_id prefix is given."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "run_id_prefix": {
                            "type": "string",
                            "description": (
                                "First 8 characters of the run ID to read. "
                                "Leave empty to read the current session."
                            ),
                        },
                    },
                    "required": ["run_id_prefix"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
    ]
