import json
import os
import time

from openai import OpenAI


def chat_complete(client, system_message, user_input, history=None, model="gpt-4o-mini", temperature=0.2):
    message = []
    message.append({"role": "system", "content": system_message})
    if history != None:
        message = message + history
    message.append({"role": "user", "content": user_input})
    chat_completion = client.chat.completions.create(
            messages=message,
            model=model,
            temperature=temperature
        )
    output = chat_completion.choices[0].message.content
    return output


def parse_bonus_reasons(bonus):
    bonus_reasons = []
    if bonus.startswith("[Included Bonus Points]:"):
        bonus_content = bonus.replace("[Included Bonus Points]:", "").strip()
        if "None" not in bonus_content:
            indices = bonus_content.split(",")
            for indice in indices:
                indice_str = indice.replace('(', '').replace(')', '').replace("'", "").replace("\"", "")
                is_valid = all(
                    [ch in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9') for ch in indice_str])
                if is_valid:
                    valid_indice = int(indice_str)
                    bonus_reasons.append(valid_indice)
                else:
                    return f"Invalid indice format: {indices}"
    else:
        return f"Wrong bonus format: {bonus}"

    return bonus_reasons


def scoring_answer(client, result_path, eval_out_path, dim):
    all_items = []
    with open(result_path, "r", encoding="utf-8") as rf:
        for idx, line in enumerate(rf):
            item = json.loads(line.strip())
            assert set(item.keys()) >= {'book_name', 'question', 'answer', 'bonus_points', 'response', 'tom_dimension'}
            if item['tom_dimension'] != dim:
                continue
            all_items.append(item)

    with (open(eval_out_path, "w", encoding="utf-8") as wf):
        for idx, item in enumerate(all_items, start=1):
            print(f"--------{idx}--------")
            book_name = item['book_name']
            question = item['question'].strip().replace("\n", "") if 'question' in item else None
            answer = item['answer'].strip().replace("\n", "")

            bonus_points = item['bonus_points']
            if len(bonus_points) > 0:
                bonus_points_str = '\n'.join(
                    [f"({b_id}) {b_point}" for b_id, b_point in enumerate(bonus_points, start=1)])
            else:
                bonus_points_str = ""

            model_response = item['response']
            trunc_len = max(len(answer.split(' ')) + 5, int(1.5 * len(answer.split(' '))))
            model_response = ' '.join(model_response.split(' ')[:trunc_len])

            system_message = (
                f"Assuming you are an expert in psychology and literary. Based on your profound understanding of the story in the book ${book_name}, assess the quality of the [Response] to the given [Question] according to the provided [Reference Answer] and corresponding [Bonus Points].")
            user_input_head = f"The following gives the [Question], [Reference Answer] and corresponding [Bonus Points]."
            user_input = f"""{user_input_head}\n\n""" \
                         + f"""[Question]\n{question}\n""" \
                         + f"""[Reference Answer]\n{answer}\n""" \
                         + f"""[Bonus Points]\n{bonus_points_str}\n\n""" \
                         + f"""[Response]\n{model_response}\n\n""" \
                         + f"""You are supposed to assess the quality of the [Response] and indicate which [Bonus Points] are explicitly or implicitly included in the [Response].\n""" \
                         + f"""Note that: 1. The [Reference Answer] and [Bonus Points] must be the core basis of assessment.\n""" \
                         + f"""2. The response may be similar to a certain bonus point but with different wording. As long as it expresses a similar meaning to this bonus point with no error, the point can be considered to be validly included.\n""" \
                         + f"""3. If the response does not include any bonus point, just output '[Included Bonus Points]: None'\n\n""" \
                         + f"""Please conform to the following format: [Included Bonus Points]: \"<Indices of the included bonus points separated by commas, such as 1,2>\""""
            response = chat_complete(client, system_message, user_input)

            response = response.replace("\n\n", "\n").strip()
            print(response)
            split_response = response.split("\n")

            bonus_reasons = "Null"
            if len(split_response) == 1:
                bonus_str = response.strip()
                parsed_bonus_reasons = parse_bonus_reasons(bonus_str)
                if type(parsed_bonus_reasons) == list:
                    bonus_reasons = parsed_bonus_reasons
                elif type(parsed_bonus_reasons) == str:
                    print(f"Error at {idx}", parsed_bonus_reasons)
                else:
                    print(f"Error at {idx}")
            else:
                print(f"Wrong response format at {idx}: ", response)

            item['bonus'] = bonus_reasons
            wf.write(json.dumps(item, ensure_ascii=False) + "\n")


def criticize_answer(client, eval_out_path, criticize_out_path, context_length):
    all_items = []
    with open(eval_out_path, "r", encoding="utf-8") as rf:
        for idx, line in enumerate(rf):
            item = json.loads(line.strip())
            assert set(item.keys()) >= {'book_name', 'question', 'answer', 'response', f'context_{context_length}'}
            all_items.append(item)

    with (open(criticize_out_path, "w", encoding="utf-8") as wf):
        for idx, item in enumerate(all_items, start=1):
            print(f"--------{idx}--------")
            book_name = item['book_name']
            background_context = item[f'context_{context_length}'].strip()
            question = item['question'].strip().replace("\n", "") if 'question' in item else None
            answer = item['answer'].strip().replace("\n", "")

            model_response = item['response']
            trunc_len = max(len(answer.split(' ')) + 5, int(1.5 * len(answer.split(' '))))
            model_response = ' '.join(model_response.split(' ')[:trunc_len])

            system_message = (
                f"Assuming you are an expert in psychology and literary. Based on your profound understanding of the story in the book ${book_name}, you are supposed to detect any defect existing in the [Response] to the [Question].")
            user_input_head = f"The following gives the [Story Plot], [Question], [Reference Answer] and corresponding [Response]."
            user_input = f"""{user_input_head}\n\n""" \
                         + f"""[Story Plot]\n{background_context}\n\n""" \
                         + f"""[Question]\n{question}\n""" \
                         + f"""[Reference Answer]\n{answer}\n""" \
                         + f"""[Response]\n{model_response}\n\n""" \
                         + f"""Please use the content in the [Story Plot] and [Reference Answer] as the basis for assessing the [Response], and point out the [Defects] in the answer.""" \
                         + f"""Note that: 1. The [Reference Answer] and [Story Plot] must be the core basis for detecting [Defects] in the [Response]. \n""" \
                         + f"""2. [Defects] refers to factual or logical errors in the [Response].\n""" \
                         + f"""3. Do not reluctantly find defects when the response is totally reasonable. If there is no defect, just output ‘[Defects]: None’\n\n""" \
                         + f"""Please conform to the following format:\n[Defects]: defects in the response."""
            response = chat_complete(client, system_message, user_input)
            response = response.strip()
            print("[Question]:", question)
            print("[Reference Answer]:", answer)
            print("[Response]:", model_response)
            print(response)

            penalty_reason = "Null"
            if response.startswith("[Defects]:"):
                penalty_reason = response.replace("[Defects]:", "").strip()
            else:
                print(f"Wrong penalty format at {idx}: ", response)
            item['penalty'] = penalty_reason
            wf.write(json.dumps(item, ensure_ascii=False) + "\n")


def collect_eval_results(eval_out_path):
    print(f"Start evaluating {eval_out_path}")
    all_items = []
    with open(eval_out_path, "r", encoding="utf-8") as rf:
        for idx, line in enumerate(rf):
            line = line.strip()
            if not line.startswith("{"):
                break
            item = json.loads(line.strip())
            assert set(item.keys()) >= {'answer', 'bonus_points', 'response', 'bonus', 'penalty'}
            all_items.append(item)

    num_bonus_points = 0
    num_bonus = 0
    num_penalty = 0
    total_num_answer_tokens = 0
    total_num_response_tokens = 0
    for idx, item in enumerate(all_items, start=1):
        answer = item['answer']
        total_num_answer_tokens += len(answer)
        response = item['response']
        total_num_response_tokens += len(response)
        bonus_points = item['bonus_points']
        bonus = set(item['bonus'])
        penalty = item['penalty']
        num_bonus_points += len(bonus_points)
        num_bonus += len(bonus)

        if "None" not in penalty:
            num_penalty += 1

    print(f"Finish evaluating {eval_out_path}")
    result_str = f"Evaluation Results:\n" \
                 f"Number of bonus points: {num_bonus_points}\n" \
                 f"Number of bonus: {num_bonus}, Coverage: {num_bonus / num_bonus_points:.3f}\n" \
                 f"Number of penalty: {num_penalty}, Rate of penalty: {num_penalty / len(all_items):.3f}\n" \
                 f"Total number of response tokens: {total_num_response_tokens}, Total number of answer tokens: {total_num_answer_tokens}, Rate of token numbers: {total_num_response_tokens / total_num_answer_tokens:.3f}\n"
    print(result_str)
    return total_num_response_tokens, total_num_answer_tokens


if __name__ == '__main__':
    api_key = os.getenv("OPENAI_API_KEY")
    assert api_key is not None
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(api_key=api_key, base_url=base_url)

    model_names = ["gpt-4o", "gpt-3.5-turbo-1106", "qwen2-7b-chat", "llama-3.1-8B-instruct", "mistral-7b-instruct-v0.3", "internlm2-chat-7b"]
    tom_dimensions = ["belief", "desire", "emotion", "intention"]
    context_lengths = [0, 1000, 2000]

    for model_name in model_names:
        total_num_response_tokens, total_num_answer_tokens = 0, 0
        for dim in tom_dimensions:
            for context_length in context_lengths:
                result_path = f"output/{model_name}_c{context_length}_answer.jsonl"
                assert os.path.exists(result_path), f"Result file {result_path} does not exist"
                eval_out_path = f"output/{model_name}_{dim}_c{context_length}_eval.jsonl"
                criticize_out_path = f"output/{model_name}_{dim}_c{context_length}_eval_penalty.jsonl"

                scoring_answer(client, result_path, eval_out_path, dim)
                criticize_answer(client, eval_out_path, criticize_out_path, context_length)
                num_response_tokens, num_answer_tokens = collect_eval_results(criticize_out_path)
                total_num_response_tokens += num_response_tokens
                total_num_answer_tokens += num_answer_tokens

        print(f"Model: {model_name}; Rate of token numbers: {total_num_response_tokens/total_num_answer_tokens:.3f}")
        print(f"Model: {model_name}; Rate of token numbers: {total_num_response_tokens/total_num_answer_tokens:.3f}")
