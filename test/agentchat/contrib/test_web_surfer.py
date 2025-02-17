import os
import sys
import re
import pytest
from autogen import ConversableAgent, UserProxyAgent, config_list_from_json
from autogen.oai.openai_utils import filter_config

sys.path.append(os.path.join(os.path.dirname(__file__), "../.."))
from conftest import skip_openai  # noqa: E402

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from test_assistant_agent import KEY_LOC, OAI_CONFIG_LIST  # noqa: E402

BLOG_POST_URL = "https://microsoft.github.io/autogen/blog/2023/04/21/LLM-tuning-math"
BLOG_POST_TITLE = "Does Model and Inference Parameter Matter in LLM Applications? - A Case Study for MATH | AutoGen"
BING_QUERY = "Microsoft"

try:
    from autogen.agentchat.contrib.web_surfer import WebSurferAgent
except ImportError:
    skip_all = True
else:
    skip_all = False

try:
    from openai import OpenAI
except ImportError:
    skip_oai = True
else:
    skip_oai = False or skip_openai

try:
    BING_API_KEY = os.environ["BING_API_KEY"]
except KeyError:
    skip_bing = True
else:
    skip_bing = False

if not skip_oai:
    config_list = config_list_from_json(env_or_file=OAI_CONFIG_LIST, file_location=KEY_LOC)


@pytest.mark.skipif(
    skip_all,
    reason="do not run if dependency is not installed",
)
def test_web_surfer():
    page_size = 4096
    web_surfer = WebSurferAgent("web_surfer", llm_config=False, browser_config={"viewport_size": page_size})

    # Sneak a peak at the function map, allowing us to call the functions for testing here
    function_map = web_surfer._user_proxy._function_map

    # Test some basic navigations
    response = function_map["visit_page"](BLOG_POST_URL)
    assert f"Address: {BLOG_POST_URL}".strip() in response
    assert f"Title: {BLOG_POST_TITLE}".strip() in response

    # Test scrolling
    m = re.search(r"\bViewport position: Showing page 1 of (\d+).", response)
    total_pages = int(m.group(1))

    response = function_map["page_down"]()
    assert (
        f"Viewport position: Showing page 2 of {total_pages}." in response
    )  # Assumes the content is longer than one screen

    response = function_map["page_up"]()
    assert f"Viewport position: Showing page 1 of {total_pages}." in response

    # Try to scroll too far back up
    response = function_map["page_up"]()
    assert f"Viewport position: Showing page 1 of {total_pages}." in response

    # Try to scroll too far down
    for i in range(0, total_pages + 1):
        response = function_map["page_down"]()
    assert f"Viewport position: Showing page {total_pages} of {total_pages}." in response

    # Test web search -- we don't have a key in this case, so we expect it to raise an error (but it means the code path is correct)
    with pytest.raises(ValueError, match="Missing Bing API key."):
        response = function_map["informational_web_search"](BING_QUERY)

    with pytest.raises(ValueError, match="Missing Bing API key."):
        response = function_map["navigational_web_search"](BING_QUERY)

    # Test Q&A and summarization -- we don't have a key so we expect it to fail (but it means the code path is correct)
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'create'"):
        response = function_map["answer_from_page"]("When was it founded?")

    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'create'"):
        response = function_map["summarize_page"]()


@pytest.mark.skipif(
    skip_oai,
    reason="do not run if oai is not installed",
)
def test_web_surfer_oai():
    llm_config = {"config_list": config_list, "timeout": 180, "cache_seed": None}

    summarizer_llm_config = {
        "config_list": filter_config(
            config_list, {"model": ["gpt-3.5-turbo-1106", "gpt-3.5-turbo-16k-0613", "gpt-3.5-turbo-16k"]}
        ),
        "timeout": 180,
        "cache_seed": None,
    }

    assert len(llm_config["config_list"]) > 0
    assert len(summarizer_llm_config["config_list"]) > 0

    page_size = 4096
    web_surfer = WebSurferAgent(
        "web_surfer",
        llm_config=llm_config,
        summarizer_llm_config=summarizer_llm_config,
        browser_config={"viewport_size": page_size},
    )

    user_proxy = UserProxyAgent(
        "user_proxy",
        human_input_mode="NEVER",
        code_execution_config=False,
        default_auto_reply="",
        is_termination_msg=lambda x: True,
    )

    # Make some requests that should test function calling
    user_proxy.initiate_chat(web_surfer, message="Please visit the page 'https://en.wikipedia.org/wiki/Microsoft'")

    user_proxy.initiate_chat(web_surfer, message="Please scroll down.")

    user_proxy.initiate_chat(web_surfer, message="Please scroll up.")

    user_proxy.initiate_chat(web_surfer, message="When was it founded?")

    user_proxy.initiate_chat(web_surfer, message="What's this page about?")


@pytest.mark.skipif(
    skip_bing,
    reason="do not run if bing api key is not available",
)
def test_web_surfer_bing():
    page_size = 4096
    web_surfer = WebSurferAgent(
        "web_surfer",
        llm_config=False,
        browser_config={"viewport_size": page_size, "bing_api_key": BING_API_KEY},
    )

    # Sneak a peak at the function map, allowing us to call the functions for testing here
    function_map = web_surfer._user_proxy._function_map

    # Test informational queries
    response = function_map["informational_web_search"](BING_QUERY)
    assert f"Address: bing: {BING_QUERY}" in response
    assert f"Title: {BING_QUERY} - Search" in response
    assert "Viewport position: Showing page 1 of 1." in response
    assert f"A Bing search for '{BING_QUERY}' found " in response

    # Test informational queries
    response = function_map["navigational_web_search"](BING_QUERY + " Wikipedia")
    assert "Address: https://en.wikipedia.org/wiki/" in response


if __name__ == "__main__":
    """Runs this file's tests from the command line."""
    test_web_surfer()
    # test_web_surfer_oai()
    # test_web_surfer_bing()
