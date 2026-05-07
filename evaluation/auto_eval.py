import argparse
import os
import json
import time
import re
import base64

from openai import OpenAI

SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS' or 'NOT SUCCESS'."""
USER_PROMPT = """TASK: <task>
Result Response: <answer>
<num> screenshots at the end: """


def load_env_file(env_path):
    env_values = {}
    if not env_path or not os.path.exists(env_path):
        return env_values

    with open(env_path, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if key.startswith('export '):
                key = key[len('export '):].strip()
            value = value.strip().strip('"').strip("'")
            env_values[key] = value
            os.environ.setdefault(key, value)
    return env_values


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def auto_eval_by_gpt4v(process_dir, openai_client, api_model, img_num, max_retries):
    print(f'--------------------- {process_dir} ---------------------')
    res_files = sorted(os.listdir(process_dir))
    with open(os.path.join(process_dir, 'interact_messages.json')) as fr:
        it_messages = json.load(fr)

    if len(it_messages) == 1:
        print('Not find answer for ' + process_dir + ' only system messages')
        print()
        return 0

    task_info = it_messages[1]["content"]
    if type(task_info) == list:
        task_info = task_info[0]["text"]
    assert 'Now given a task' in task_info
    pattern = r"Now given a task:(.+?)Please interact with"
    matches = re.search(pattern, task_info)
    task_content = matches.group(1).strip()

    ans_info = it_messages[-1]["content"]
    if 'Action: ANSWER' not in ans_info:
        print('Not find answer for ' + process_dir)
        print()
        return 0
    pattern_ans = r"ANSWER[; ]+\[?(.[^\]]*)\]?"
    matches_ans = re.search(pattern_ans, ans_info)
    answer_content = matches_ans.group(1).strip()

    # max_screenshot_id = max([int(f[10:].split('.png')[0]) for f in os.listdir(process_dir) if '.png' in f])
    # final_screenshot = f'screenshot{max_screenshot_id}.png'
    # b64_img = encode_image(os.path.join(process_dir, final_screenshot))
    whole_content_img = []
    pattern_png = r'screenshot(\d+)\.png'
    matches = [(filename, int(re.search(pattern_png, filename).group(1))) for filename in res_files if re.search(pattern_png, filename)]
    matches.sort(key=lambda x: x[1])
    end_files = matches[-img_num:]
    for png_file in end_files:
        b64_img = encode_image(os.path.join(process_dir, png_file[0]))
        whole_content_img.append(
            {
                'type': 'image_url',
                'image_url': {"url": f"data:image/png;base64,{b64_img}"}
            }
        )

    user_prompt_tmp = USER_PROMPT.replace('<task>', task_content)
    user_prompt_tmp = user_prompt_tmp.replace('<answer>', answer_content)
    user_prompt_tmp = user_prompt_tmp.replace('<num>', str(img_num))
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': user_prompt_tmp}
            ]
            + whole_content_img
            + [{'type': 'text', 'text': "Your verdict:\n"}]
        }
    ]
    attempts = 0
    while True:
        try:
            print('Calling gpt4v API to get the auto evaluation......')
            openai_response = openai_client.chat.completions.create(
                model=api_model, messages=messages, max_tokens=1000, seed=42, temperature=0
            )
            print('Prompt Tokens:', openai_response.usage.prompt_tokens, ';',
                  'Completion Tokens:', openai_response.usage.completion_tokens)
            print('Cost:', openai_response.usage.prompt_tokens/1000 * 0.01
                  + openai_response.usage.completion_tokens / 1000 * 0.03)

            print('API call complete...')
            break
        except Exception as e:
            attempts += 1
            print(e)
            error_name = type(e).__name__
            if error_name in {'BadRequestError', 'AuthenticationError', 'PermissionDeniedError',
                              'NotFoundError', 'InvalidRequestError'}:
                raise
            if attempts >= max_retries:
                raise
            if error_name == 'RateLimitError':
                time.sleep(10)
            elif error_name == 'APIError':
                time.sleep(15)
            else:
                time.sleep(10)
    gpt_4v_res = openai_response.choices[0].message.content
    print_message = messages[1]
    for idx in range(len(print_message['content'])):
        if print_message['content'][idx]['type'] == 'image_url':
            print_message['content'][idx]['image_url'] = {"url": "data:image/png;base64, b64_img"}

    # print_message[1]['content'][1]['image_url'] = {"url": "data:image/png;base64, b64_img"}
    print(print_message)
    print(gpt_4v_res)

    auto_eval_res = 0 if 'NOT SUCCESS' in gpt_4v_res else 1
    if 'SUCCESS' not in gpt_4v_res:
        auto_eval_res = None
    print('Auto_eval_res:', auto_eval_res)
    print()
    return auto_eval_res


def validate_eval_input(process_dir):
    interact_path = os.path.join(process_dir, 'interact_messages.json')
    if not os.path.exists(interact_path):
        return False, 'missing interact_messages.json'

    try:
        with open(interact_path, encoding='utf-8') as fr:
            it_messages = json.load(fr)
    except Exception as e:
        return False, f'invalid interact_messages.json: {e}'

    if len(it_messages) < 2:
        return False, 'interact_messages.json has fewer than 2 messages'

    task_info = it_messages[1].get("content")
    if type(task_info) == list:
        task_info = task_info[0].get("text", "")
    if not isinstance(task_info, str) or 'Now given a task' not in task_info:
        return False, 'missing task marker'

    ans_info = it_messages[-1].get("content")
    if not isinstance(ans_info, str) or 'Action: ANSWER' not in ans_info:
        return False, 'missing final Action: ANSWER'

    pattern_png = r'screenshot(\d+)\.png'
    screenshots = [filename for filename in os.listdir(process_dir) if re.search(pattern_png, filename)]
    if not screenshots:
        return False, 'missing screenshotN.png files'

    return True, f'ok screenshots={len(screenshots)}'


def scan_task_dirs(process_dir, recursive=False):
    if recursive:
        task_dirs = []
        for root, _dirs, files in os.walk(process_dir):
            if 'interact_messages.json' in files:
                task_dirs.append(root)
        return sorted(task_dirs)

    return sorted(
        os.path.join(process_dir, name)
        for name in os.listdir(process_dir)
        if os.path.isdir(os.path.join(process_dir, name))
        and os.path.exists(os.path.join(process_dir, name, 'interact_messages.json'))
    )


def append_summary(summary_file, record):
    if not summary_file:
        return
    summary_dir = os.path.dirname(summary_file)
    if summary_dir:
        os.makedirs(summary_dir, exist_ok=True)
    with open(summary_file, 'a', encoding='utf-8') as fw:
        fw.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--process_dir', type=str, default='results')
    parser.add_argument('--lesson_dir', type=str, default='results')
    parser.add_argument("--api_key", default="key", type=str, help="YOUR_OPENAI_API_KEY")
    parser.add_argument("--api_model", default="gpt-4-vision-preview", type=str, help="api model name")
    parser.add_argument("--api_base", default=None, type=str, help="OpenAI-compatible API base URL")
    parser.add_argument("--env_file", default=".env", type=str, help="Environment file for API settings")
    parser.add_argument("--max_attached_imgs", type=int, default=1)
    parser.add_argument("--scan_tasks", action='store_true', help="Scan process_dir for task dirs with interact_messages.json")
    parser.add_argument("--recursive", action='store_true', help="Recursively scan process_dir when --scan_tasks is set")
    parser.add_argument("--summary_file", type=str, default=None, help="Optional JSONL summary output")
    parser.add_argument("--dry_run", action='store_true', help="Validate inputs without calling the evaluation model")
    parser.add_argument("--max_retries", type=int, default=3, help="Maximum retries for each evaluation API call")
    args = parser.parse_args()

    env_values = load_env_file(args.env_file)
    if args.api_key == "key":
        args.api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("DOUBAO_API_KEY")
            or env_values.get("OPENAI_API_KEY")
            or env_values.get("DOUBAO_API_KEY")
            or args.api_key
        )
    if args.api_model == "gpt-4-vision-preview":
        args.api_model = (
            os.getenv("OPENAI_API_MODEL")
            or os.getenv("DOUBAO_API_MODEL")
            or env_values.get("OPENAI_API_MODEL")
            or env_values.get("DOUBAO_API_MODEL")
            or args.api_model
        )
    if not args.api_base:
        args.api_base = (
            os.getenv("OPENAI_API_BASE")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("DOUBAO_API_URL")
            or env_values.get("OPENAI_API_BASE")
            or env_values.get("OPENAI_BASE_URL")
            or env_values.get("DOUBAO_API_URL")
        )

    client = None
    if not args.dry_run:
        if not args.api_key or args.api_key == "key":
            raise ValueError("Missing API key. Set OPENAI_API_KEY/DOUBAO_API_KEY in .env or pass --api_key.")
        client_kwargs = {"api_key": args.api_key}
        if args.api_base:
            client_kwargs["base_url"] = args.api_base
        client = OpenAI(**client_kwargs)

    if args.scan_tasks:
        task_dirs = scan_task_dirs(args.process_dir, args.recursive)
        print(f'Found {len(task_dirs)} task dirs under {args.process_dir}')
        for file_dir in task_dirs:
            if args.dry_run:
                ok, reason = validate_eval_input(file_dir)
                response = 1 if ok else 0
                print(f'[{response}] {file_dir}: {reason}')
            else:
                try:
                    response = auto_eval_by_gpt4v(
                        file_dir, client, args.api_model, args.max_attached_imgs, args.max_retries
                    )
                    reason = None
                except Exception as e:
                    response = None
                    reason = f'{type(e).__name__}: {e}'
                    print(f'[ERROR] {file_dir}: {reason}')
            append_summary(args.summary_file, {
                "task_dir": file_dir,
                "auto_eval_res": response,
                "dry_run": args.dry_run,
                "reason": reason,
            })
        return

    webs = ['Allrecipes', 'Amazon', 'Apple', 'ArXiv', 'BBC News', 'Booking', 'Cambridge Dictionary',
            'Coursera', 'ESPN', 'GitHub', 'Google Flights', 'Google Map', 'Google Search', 'Huggingface', 'Wolfram Alpha']

    for web in webs:
        web_task_res = []
        for idx in range(0, 46):
            file_dir = os.path.join(args.process_dir, 'task'+web+'--'+str(idx))
            if os.path.exists(file_dir):
                if args.dry_run:
                    ok, reason = validate_eval_input(file_dir)
                    response = 1 if ok else 0
                    print(f'[{response}] {file_dir}: {reason}')
                else:
                    try:
                        response = auto_eval_by_gpt4v(
                            file_dir, client, args.api_model, args.max_attached_imgs, args.max_retries
                        )
                        reason = None
                    except Exception as e:
                        response = None
                        reason = f'{type(e).__name__}: {e}'
                        print(f'[ERROR] {file_dir}: {reason}')
                web_task_res.append(response)
                append_summary(args.summary_file, {
                    "task_dir": file_dir,
                    "auto_eval_res": response,
                    "dry_run": args.dry_run,
                    "reason": reason,
                })
            else:
                pass
        if web_task_res:
            print(web_task_res)
if __name__ == '__main__':
    main()
