# mypy: ignore-errors

import pathlib
import sys
import types

from typer.testing import CliRunner

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# stub heavy optional dependencies to avoid import errors
datasets_stub = types.ModuleType("datasets")
setattr(datasets_stub, "Dataset", object)
sys.modules.setdefault("datasets", datasets_stub)

langchain_stub = types.ModuleType("langchain")
emb_stub = types.ModuleType("langchain.embeddings")
setattr(emb_stub, "SentenceTransformerEmbeddings", object)
vec_stub = types.ModuleType("langchain.vectorstores")
setattr(vec_stub, "FAISS", object)
sys.modules.setdefault("langchain", langchain_stub)
sys.modules.setdefault("langchain.embeddings", emb_stub)
sys.modules.setdefault("langchain.vectorstores", vec_stub)

for mod_name in [
    "scheduler",
    "ws_server",
    "bayesian",
    "chat_agent",
    "config",
    "fetcher",
    "gui",
    "meta_learning",
    "simulate",
]:
    full_name = f"sentiment_bot.{mod_name}"
    module = types.ModuleType(full_name)
    sys.modules.setdefault(full_name, module)

sys.modules["sentiment_bot.bayesian"].fit_hierarchical = lambda *a, **k: None
sys.modules["sentiment_bot.bayesian"].load_example_data = lambda *a, **k: None
sys.modules["sentiment_bot.chat_agent"].ChatAgent = type("ChatAgent", (), {})
sys.modules["sentiment_bot.config"].settings = types.SimpleNamespace()
sys.modules["sentiment_bot.fetcher"].fetch_and_parse = lambda *a, **k: None
sys.modules["sentiment_bot.gui"].launch = lambda: None
sys.modules["sentiment_bot.meta_learning"].MAMLTrainer = type("MAMLTrainer", (), {})
sys.modules["sentiment_bot.simulate"].monte_carlo = lambda *a, **k: None
sys.modules["sentiment_bot.simulate"].save_csv = lambda *a, **k: None

from sentiment_bot.cli import app  # noqa: E402


def test_chat_requires_api_key():
    runner = CliRunner()
    result = runner.invoke(app, ["chat"], env={"OPENAI_API_KEY": ""})
    assert result.exit_code == 0
    assert "chat" in result.output.lower()
