"""Deterministic synthetic admissions inputs; no student records."""
SCENARIOS = {
    'basic': (20, 'How can I learn whether my prior college courses may transfer into the BLS program while planning my application timeline?'),
    'background': (300, 'Please review my fictional academic background and suggest questions I should ask an admissions advisor.'),
    'outline': (500, 'Please give feedback on this fictional application essay outline and identify places needing more detail, without writing my essay.'),
    'essay': (1000, 'Please critique this fictional application essay for clarity and structure, without writing a submission for me.'),
    'drafts': (2000, 'Please compare these fictional essay drafts and suggest revisions I can make myself, without writing a submission.'),
    'academic_history': (3000, 'Please help me organize this fictional academic history and identify questions for an advisor.'),
    'documentation': (5000, 'Please help me understand this fictional program documentation and identify questions to verify with the BLS office.'),
    'extreme': (20000, 'Please summarize the questions raised by this fictional academic background for an admissions advisor.'),
}
PARAGRAPHS = [
    'I attended a community college while working part time and explored courses in history, writing, and mathematics.',
    'My schedule changed during a family move, so I paused enrollment before returning to study with a clearer plan.',
    'I hope to connect prior learning with future work, and I would like to understand transfer credit and advising options.',
    'One experience involved collaborating on a community project where I learned to listen carefully and revise my assumptions.',
    'A later course helped me develop research habits, evaluate sources, and explain complicated ideas to different audiences.',
]

def make_scenario(name):
    target, prompt = SCENARIOS[name]
    words = prompt.split()
    if len(words) > target:
        raise ValueError(name)
    pieces = [prompt]
    count = len(words)
    index = 0
    while count < target:
        remaining = target - count
        paragraph = PARAGRAPHS[index % len(PARAGRAPHS)].split()[:remaining]
        pieces.append(' '.join(paragraph))
        count += len(paragraph)
        index += 1
    return '\n\n'.join(pieces)

def metrics(text):
    return {'characters': len(text), 'words': len(text.split()), 'utf8_bytes': len(text.encode('utf-8'))}
