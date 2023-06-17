
from toolbox import CatchException, update_ui, write_results_to_file
from .crazy_utils import request_gpt_model_in_new_thread_with_ui_alive, input_clipping
import requests
from bs4 import BeautifulSoup
from request_llm.bridge_all import model_info

def scrape_text(url, proxies) -> str:
    """Scrape text from a webpage

    Args:
        url (str): The URL to scrape text from

    Returns:
        str: The scraped text
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36',
        'Content-Type': 'text/plain',
    }
    try: 
        response = requests.get(url, headers=headers, proxies=proxies, timeout=8)
        if response.encoding == "ISO-8859-1": response.encoding = response.apparent_encoding
    except: 
        return "无法连接到该网页"
    soup = BeautifulSoup(response.text, "html.parser")
    for script in soup(["script", "style"]):
        script.extract()
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    return text

@CatchException
def 总结单个链接的网页内容(txt, llm_kwargs, plugin_kwargs, chatbot, history, system_prompt, web_port):
    """
    txt             输入栏用户输入的文本，例如需要翻译的一段话，再例如一个包含了待处理文件的路径
    llm_kwargs      gpt模型参数，如温度和top_p等，一般原样传递下去就行
    plugin_kwargs   插件模型的参数，暂时没有用武之地
    chatbot         聊天显示框的句柄，用于显示给用户
    history         聊天历史，前情提要
    system_prompt   给gpt的静默提醒
    web_port        当前软件运行的端口号
    """
    history = []    # 清空历史，以免输入溢出
    chatbot.append((f"请读取该链接下的网页内容，并按照用户输入进行分析：{txt}", 
                    "[Local Message] MCG 自己改造的一个插件，直接读取网页链接，并提供总结。"))
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面 # 由于请求gpt需要一段时间，我们先及时地做一次界面更新

    # ------------- < 第1步：爬取搜索引擎的结果 > -------------
    from toolbox import get_conf
    proxies, = get_conf('proxies')
    # urls = google(txt, proxies)
    # history = []

    urls = [{"link":txt}]

    # ------------- < 第2步：依次访问网页 > -------------
    max_search_result = 1   # 最多收纳多少个网页的结果
    for index, url in enumerate(urls[:max_search_result]):
        res = scrape_text(url['link'], proxies)
        history.extend([f"第{index}份搜索结果：", res])
        chatbot.append([f"第{index}份搜索结果：", res[:500]+"......"])
        yield from update_ui(chatbot=chatbot, history=history) # 刷新界面 # 由于请求gpt需要一段时间，我们先及时地做一次界面更新

    # ------------- < 第3步：ChatGPT综合 > -------------
    # i_say = f"将以上信息作为一个完整的文章内容，并输出总结结果。"
    # i_say, history = input_clipping(    # 裁剪输入，从最长的条目开始裁剪，防止爆token
    #     inputs=i_say, 
    #     history=history, 
    #     max_token_limit=model_info[llm_kwargs['llm_model']]['max_token']*3//4
    # )
    # gpt_say = yield from request_gpt_model_in_new_thread_with_ui_alive(
    #     inputs=i_say, inputs_show_user=i_say, 
    #     llm_kwargs=llm_kwargs, chatbot=chatbot, history=history, 
    #     sys_prompt="请从给定的若干条搜索结果中抽取信息，回答用户提出的问题。"
    # )
    # chatbot[-1] = (i_say, gpt_say)
    # history.append(i_say);history.append(gpt_say)
    # yield from update_ui(chatbot=chatbot, history=history) # 刷新界面 # 界面更新

    # ------------- < 第4步：复用 总结word文档.py 的代码 > -------------
    file_content = res
    from .crazy_utils import breakdown_txt_to_satisfy_token_limit_for_pdf
    from request_llm.bridge_all import model_info
    max_token = model_info[llm_kwargs['llm_model']]['max_token']
    TOKEN_LIMIT_PER_FRAGMENT = max_token * 3 // 4
    paper_fragments = breakdown_txt_to_satisfy_token_limit_for_pdf(
        txt=file_content,  
        get_token_fn=model_info[llm_kwargs['llm_model']]['token_cnt'], 
        limit=TOKEN_LIMIT_PER_FRAGMENT
    )
    this_paper_history = []
    for i, paper_frag in enumerate(paper_fragments):
        i_say = f'请对下面的文章片段用中文做概述，这是第{i+1}/{len(paper_fragments)}段，文章内容是 ```{paper_frag}```'
        i_say_show_user = f'请对下面的文章片段做概述: 第{i+1}/{len(paper_fragments)}个片段。'
        gpt_say = yield from request_gpt_model_in_new_thread_with_ui_alive(
            inputs=i_say, 
            inputs_show_user=i_say_show_user, 
            llm_kwargs=llm_kwargs,
            chatbot=chatbot, 
            history=[],
            sys_prompt="总结文章。"
        )

        chatbot[-1] = (i_say_show_user, gpt_say)
        history.extend([i_say_show_user,gpt_say])
        this_paper_history.extend([i_say_show_user,gpt_say])

    # 已经对该文章的所有片段总结完毕，如果文章被切分了，
    if len(paper_fragments) > 1:
        i_say = f"根据以上的对话，总结文章的主要内容。"
        gpt_say = yield from request_gpt_model_in_new_thread_with_ui_alive(
            inputs=i_say, 
            inputs_show_user=i_say, 
            llm_kwargs=llm_kwargs,
            chatbot=chatbot, 
            history=this_paper_history,
            sys_prompt="总结文章。"
        )

        history.extend([i_say,gpt_say])
        this_paper_history.extend([i_say,gpt_say])

    res = write_results_to_file(history)
    chatbot.append(("完成了吗？", res))
    yield from update_ui(chatbot=chatbot, history=history) # 刷新界面
