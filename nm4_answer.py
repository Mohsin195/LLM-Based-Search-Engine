def generate_answer(question, df, call_openai_with_retry, detect_question_language, conversation_history=None):
    language_hint = detect_question_language(question)

    context_section = ""
    if conversation_history and len(conversation_history) > 0:
        context_section = "\n=== CONVERSATION CONTEXT ===\n"
        recent_history = conversation_history[-8:] if len(conversation_history) > 8 else conversation_history
        for i, msg in enumerate(recent_history, 1):
            role_label = "User" if msg["role"] == "user" else "Assistant"
            context_section += f"[{i}] {role_label}: {msg['content'][:500]}\n"
        context_section += "\n=== CURRENT QUESTION ===\n"
        context_section += f"{question}\n\n"

    row_count = len(df)
    has_data = row_count > 0

    prompt = f"""
You are an expert financial data analyst. Your role is to provide clear, insightful, and comprehensive answers based on database query results.
{context_section}
User Question:
{question}

RESPONSE LANGUAGE:
- Detected language: {language_hint}
- Respond in the SAME language as the question
- Use ArabicName for Arabic responses, EnglishName for English responses

DATA CONTEXT:
- Column names may appear duplicated due to table joins, but each belongs to its original table context
- EnglishName = Customer name in English
- ArabicName = Customer name in Arabic
- Do NOT display GUID IDs in your response
- Row count in result: {row_count}

QUERY RESULTS:
{df.to_string(index=False) if has_data else "No data found matching the criteria."}

INSTRUCTIONS FOR YOUR RESPONSE:

1. **ANSWER STRUCTURE** (follow this format):
   - Start with a direct answer to the question
   - Provide specific numbers, names, or values from the data
   - Add context or interpretation when relevant
   - If it's a follow-up question, reference previous information appropriately

2. **CLARITY REQUIREMENTS**:
   - Use clear, professional business language
   - Format numbers appropriately (e.g., currency, percentages)
   - Highlight key insights or notable patterns
   - If showing multiple items, organize them logically (e.g., ranked by value)

3. **DATA PRESENTATION**:
   - For single values: State them clearly with context
   - For lists: Present top items (if many, show top 5-10)
   - For comparisons: Explain the difference or relationship
   - For trends: Describe the pattern observed
   - For aggregations: Explain what the total/average represents

4. **ENHANCED EXPLANATION**:
   - Explain WHAT the data shows
   - Explain WHY it might be significant (if applicable)
   - Add brief business context when helpful
   - If surprising or notable, mention it

5. **EDGE CASES**:
   - If no data found: Explain possible reasons
   - If unexpected results: Acknowledge and explain
   - If partial data: Mention limitations

6. **FORMATTING TIPS**:
   - Use bullet points for multiple items
   - Use bold for important numbers or names when appropriate
   - Keep paragraphs short and readable
   - Use proper punctuation and grammar

EXAMPLE GOOD RESPONSE:
"Based on the data, the total sales for 2025 were $1,245,680, representing a significant increase from previous periods. The top 3 customers were:

1. **ABC Corporation** - $456,000 (37% of total)
2. **XYZ Industries** - $234,500 (19% of total)  
3. **Global Trading** - $189,200 (15% of total)

These three customers alone account for 71% of total sales, indicating a strong concentration in key accounts."

Now provide your detailed, well-explained answer:
"""

    response = call_openai_with_retry(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    return response.choices[0].message.content
