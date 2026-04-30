import importlib
import sqlite3
import sys
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1]

EFFIE_LID = "272751982018765@lid"
EFFIE_PHONE = "972525314213"
EFFIE_ALIAS = "אפי עוד פרילנס"
SELF_LID = "129386544119851@lid"
SELF_PHONE = "972547589755"
SELF_ALIAS = "Etan Heyman"
UNMAPPED_LID = "72585064759394@lid"
UNMAPPED_RAW_NAME = "72585064759394"


def load_whatsapp_module(monkeypatch, messages_db_path: Path, whatsmeow_db_path: Path | None = None):
    monkeypatch.setenv("WHATSAPP_DB_PATH", str(messages_db_path))
    if whatsmeow_db_path is None:
        monkeypatch.delenv("WHATSAPP_WHATSMEOW_DB_PATH", raising=False)
    else:
        monkeypatch.setenv("WHATSAPP_WHATSMEOW_DB_PATH", str(whatsmeow_db_path))

    monkeypatch.syspath_prepend(str(SERVER_DIR))
    sys.modules.pop("whatsapp", None)
    return importlib.import_module("whatsapp")


def create_messages_db(db_path: Path, chats: list[dict[str, str]]) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE chats (
                jid TEXT PRIMARY KEY,
                name TEXT,
                last_message_time TIMESTAMP
            );

            CREATE TABLE messages (
                timestamp TIMESTAMP,
                sender TEXT,
                content TEXT,
                is_from_me BOOLEAN,
                chat_jid TEXT,
                id TEXT PRIMARY KEY,
                media_type TEXT
            );
            """
        )

        for index, chat in enumerate(chats, start=1):
            conn.execute(
                "INSERT INTO chats (jid, name, last_message_time) VALUES (?, ?, ?)",
                (chat["jid"], chat["name"], chat["timestamp"]),
            )
            conn.execute(
                """
                INSERT INTO messages (timestamp, sender, content, is_from_me, chat_jid, id, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat["timestamp"],
                    chat.get("sender", chat["jid"]),
                    chat.get("content", f"message-{index}"),
                    0,
                    chat["jid"],
                    chat.get("message_id", f"msg-{index}"),
                    None,
                ),
            )


def create_whatsmeow_db(
    db_path: Path,
    lid_map_rows: list[tuple[str, str]] | None = None,
    contact_rows: list[tuple[str, str, str, str, str]] | None = None,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE whatsmeow_lid_map (
                lid TEXT PRIMARY KEY,
                pn TEXT UNIQUE NOT NULL
            );

            CREATE TABLE whatsmeow_contacts (
                our_jid TEXT,
                their_jid TEXT,
                first_name TEXT,
                full_name TEXT,
                push_name TEXT,
                PRIMARY KEY (our_jid, their_jid)
            );
            """
        )

        conn.executemany(
            "INSERT INTO whatsmeow_lid_map (lid, pn) VALUES (?, ?)",
            lid_map_rows or [],
        )
        conn.executemany(
            """
            INSERT INTO whatsmeow_contacts (our_jid, their_jid, first_name, full_name, push_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            contact_rows or [],
        )


def setup_chat_store(tmp_path: Path, chats: list[dict[str, str]], with_whatsmeow: bool = True):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    messages_db = store_dir / "messages.db"
    create_messages_db(messages_db, chats)

    whatsmeow_db = store_dir / "whatsapp.db"
    if with_whatsmeow:
        create_whatsmeow_db(
            whatsmeow_db,
            lid_map_rows=[
                ("272751982018765", EFFIE_PHONE),
                ("129386544119851", SELF_PHONE),
            ],
            contact_rows=[
                ("me@s.whatsapp.net", f"{EFFIE_PHONE}@s.whatsapp.net", "אפי", EFFIE_ALIAS, "Efi A"),
                ("me@s.whatsapp.net", f"{SELF_PHONE}@s.whatsapp.net", "Etan", SELF_ALIAS, "Etan"),
            ],
        )

    return messages_db, whatsmeow_db


def test_list_chats_resolves_hebrew_name(monkeypatch, tmp_path):
    messages_db, _ = setup_chat_store(
        tmp_path,
        chats=[{"jid": EFFIE_LID, "name": "129386544119851", "timestamp": "2026-04-30T10:00:00"}],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db)

    chats = whatsapp.list_chats(query="אפי")

    assert len(chats) == 1
    assert chats[0].jid == EFFIE_LID
    assert chats[0].name == EFFIE_ALIAS


def test_search_contacts_resolves_hebrew_name(monkeypatch, tmp_path):
    messages_db, _ = setup_chat_store(
        tmp_path,
        chats=[{"jid": EFFIE_LID, "name": "129386544119851", "timestamp": "2026-04-30T10:00:00"}],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db)

    contacts = whatsapp.search_contacts("אפי")

    assert len(contacts) == 1
    assert contacts[0].jid == EFFIE_LID
    assert contacts[0].name == EFFIE_ALIAS


def test_falls_back_when_whatsmeow_db_missing(monkeypatch, tmp_path):
    messages_db, _ = setup_chat_store(
        tmp_path,
        chats=[{"jid": EFFIE_LID, "name": "Legacy Contact", "timestamp": "2026-04-30T10:00:00"}],
        with_whatsmeow=False,
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db)

    chats = whatsapp.list_chats(query="Legacy")

    assert len(chats) == 1
    assert chats[0].name == "Legacy Contact"


def test_falls_back_when_lid_not_in_map(monkeypatch, tmp_path):
    messages_db, whatsmeow_db = setup_chat_store(
        tmp_path,
        chats=[{"jid": UNMAPPED_LID, "name": UNMAPPED_RAW_NAME, "timestamp": "2026-04-30T10:00:00"}],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db, whatsmeow_db)

    chats = whatsapp.list_chats(query=UNMAPPED_RAW_NAME)

    assert len(chats) == 1
    assert chats[0].jid == UNMAPPED_LID
    assert chats[0].name == UNMAPPED_RAW_NAME


def test_resolves_effie_lid(monkeypatch, tmp_path):
    messages_db, _ = setup_chat_store(
        tmp_path,
        chats=[{"jid": EFFIE_LID, "name": "129386544119851", "timestamp": "2026-04-30T10:00:00"}],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db)

    chats = whatsapp.list_chats(query="272751982018765@lid")

    assert len(chats) == 1
    assert chats[0].name == EFFIE_ALIAS


def test_does_not_resolve_etan_self_lid(monkeypatch, tmp_path):
    messages_db, _ = setup_chat_store(
        tmp_path,
        chats=[
            {"jid": EFFIE_LID, "name": "129386544119851", "timestamp": "2026-04-30T10:00:00"},
            {"jid": SELF_LID, "name": "129386544119851", "timestamp": "2026-04-30T11:00:00"},
        ],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db)

    chats = whatsapp.list_chats(query=SELF_LID)

    assert len(chats) == 1
    assert chats[0].jid == SELF_LID
    assert chats[0].name == SELF_ALIAS
    assert chats[0].name != EFFIE_ALIAS


def test_list_chats_deduplicates_multiple_contact_rows(monkeypatch, tmp_path):
    store_dir = tmp_path / "store"
    store_dir.mkdir()
    messages_db = store_dir / "messages.db"
    whatsmeow_db = store_dir / "whatsapp.db"

    create_messages_db(
        messages_db,
        chats=[{"jid": EFFIE_LID, "name": "129386544119851", "timestamp": "2026-04-30T10:00:00"}],
    )
    create_whatsmeow_db(
        whatsmeow_db,
        lid_map_rows=[("272751982018765", EFFIE_PHONE)],
        contact_rows=[
            ("me@s.whatsapp.net", f"{EFFIE_PHONE}@s.whatsapp.net", "אפי", EFFIE_ALIAS, "Efi A"),
            ("alt@s.whatsapp.net", f"{EFFIE_PHONE}@s.whatsapp.net", "אפי", EFFIE_ALIAS, "Efi A"),
        ],
    )
    whatsapp = load_whatsapp_module(monkeypatch, messages_db, whatsmeow_db)

    chats = whatsapp.list_chats(query="אפי")

    assert len(chats) == 1
    assert chats[0].jid == EFFIE_LID
    assert chats[0].name == EFFIE_ALIAS
