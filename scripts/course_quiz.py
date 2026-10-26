"""Single-choice quiz grading. A question is {'id', 'prompt', 'options', 'answer' (0-based), 'explain'}."""


def grade(questions, answers):
    """answers maps question id -> chosen option index (or None when unanswered)."""
    items = []
    for question in questions:
        chosen = answers.get(question['id'])
        items.append({'id': question['id'], 'prompt': question['prompt'], 'chosen': chosen,
                      'answer': question['answer'], 'correct': chosen is not None and chosen == question['answer'],
                      'explain': question['explain']})
    return {'correct': sum(item['correct'] for item in items), 'total': len(items), 'items': items}
