(function() {
  'use strict';

  var currentView = 'human';
  var articlesRendered = false;

  function toggleView() {
    var humanView = document.getElementById('human-view');
    var agentView = document.getElementById('agent-view');
    var toggleBtn = document.getElementById('view-toggle');

    if (!humanView || !agentView) return;

    if (currentView === 'human') {
      humanView.style.display = 'none';
      agentView.style.display = 'block';
      document.body.classList.add('agent-mode');
      toggleBtn.textContent = 'Human View';
      currentView = 'agent';

      if (!articlesRendered) {
        renderAgentArticles();
        articlesRendered = true;
      }
    } else {
      humanView.style.display = 'block';
      agentView.style.display = 'none';
      document.body.classList.remove('agent-mode');
      toggleBtn.textContent = 'Agent View';
      currentView = 'human';
    }
  }

  function renderAgentArticles() {
    var dataEl = document.getElementById('articles-data');
    var container = document.getElementById('agent-articles');
    if (!dataEl || !container) return;

    var articles;
    try {
      articles = JSON.parse(dataEl.textContent);
    } catch (e) {
      container.innerHTML = '<p>Error loading article data.</p>';
      return;
    }

    container.innerHTML = articles.map(function(a) {
      var tagsHtml = a.tags.map(function(t) {
        return '<code class="agent-tag">' + esc(t) + '</code>';
      }).join(' ');

      var sourcesHtml = '';
      if (a.sources && a.sources.length) {
        sourcesHtml = '<div class="agent-sources">' +
          '<span class="agent-label">sources:</span> ' +
          a.sources.map(function(s) {
            return '<a href="' + esc(s.url) + '">' + esc(s.title) + '</a>';
          }).join(' | ') +
          '</div>';
      }

      return '<div class="agent-card">' +
        '<div class="agent-card-header">' +
          '<span class="agent-label">title:</span> ' +
          '<span class="agent-value">"' + esc(a.title) + '"</span>' +
        '</div>' +
        '<div class="agent-card-meta">' +
          '<span class="agent-label">date:</span> <code>' + a.date + '</code> ' +
          '<span class="agent-label">category:</span> <code>' + esc(a.category) + '</code> ' +
          '<span class="agent-label">reporter:</span> <code>' + esc(a.reporter) + '</code>' +
        '</div>' +
        '<div class="agent-card-meta">' +
          '<span class="agent-label">tags:</span> ' + tagsHtml +
        '</div>' +
        '<div class="agent-card-summary">' +
          '<span class="agent-label">summary:</span> ' +
          '<span class="agent-value">"' + esc(a.summary) + '"</span>' +
        '</div>' +
        '<div class="agent-card-links">' +
          '<a href="' + esc(a.url_html) + '"><code>HTML</code></a> ' +
          '<a href="' + esc(a.url_md) + '"><code>Markdown</code></a>' +
        '</div>' +
        sourcesHtml +
      '</div>';
    }).join('');
  }

  function esc(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  window.toggleView = toggleView;
})();
