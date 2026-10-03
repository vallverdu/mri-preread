'use strict';
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const code = document.getElementById(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(code.textContent);
      button.textContent = 'Copied';
    } catch {
      const range = document.createRange(); range.selectNodeContents(code);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      button.textContent = 'Select + copy';
    }
    setTimeout(() => { button.textContent = 'Copy'; }, 2200);
  });
}
const repo = window.MRI_SITE?.repoUrl;
if (repo && /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/.test(repo)) {
  document.querySelectorAll('[data-repo-link]').forEach(a => { a.href = repo; a.textContent = 'View public source ↗'; });
  document.querySelectorAll('[data-repo-state]').forEach(el => { el.textContent = 'Source available on GitHub.'; });
  const code = document.getElementById('installCode');
  if (code) code.textContent = code.textContent.replace('REPOSITORY_URL', repo + '.git');
}
