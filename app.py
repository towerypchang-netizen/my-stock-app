# 多模型自動退回與重試機制
def call_gemini_with_retry(prompt, max_retries=3):
    # 使用正確且官方支援的模型名稱列表
    models_to_try = ['gemini-1.5-flash', 'gemini-2.0-flash-exp']
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < max_retries - 1:
                        time.sleep(3 * (attempt + 1))
                        continue
                elif "404" in err_msg or "NOT_FOUND" in err_msg:
                    break
                if attempt == max_retries - 1 and model_name == models_to_try[-1]:
                    raise e
    return ""