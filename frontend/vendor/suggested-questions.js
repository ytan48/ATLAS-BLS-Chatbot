(() => {
  const suggestionCount = 4;

  function shuffle(items) {
    const shuffled = [...items];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  }

  function selectSuggestedQuestions(questions) {
    const byCategory = new Map();
    const uniqueQuestions = new Set();
    for (const { question, category } of questions) {
      if (uniqueQuestions.has(question)) continue;
      uniqueQuestions.add(question);
      const group = byCategory.get(category) ?? [];
      group.push(question);
      byCategory.set(category, group);
    }

    const selected = shuffle(byCategory.values()).slice(0, suggestionCount).map(group => {
      return group[Math.floor(Math.random() * group.length)];
    });
    if (selected.length === suggestionCount) return selected;

    const remaining = [...uniqueQuestions].filter(question => !selected.includes(question));
    return selected.concat(shuffle(remaining).slice(0, suggestionCount - selected.length));
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = { selectSuggestedQuestions };
  } else {
    window.BLSSuggestions = {
      async load() {
        const response = await fetch('/assets/suggested-questions.json');
        if (!response.ok) throw new Error('Could not load the question bank.');
        return selectSuggestedQuestions(await response.json());
      },
    };
  }
})();
