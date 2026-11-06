(function () {
  var calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // The loop: the stage cycles by itself and stops longer where a person is needed.
  var STAGES = [
    ['Plan', true, 'The agent reads the repo and the ticket, then writes a plan. No code until you approve it.'],
    ['Code', false, "Written to the skills generated for this repo, so it follows the conventions already there."],
    ['Tests and checks', false, 'Your own test, lint and typecheck commands, never guessed ones.'],
    ['Self-test', false, 'The agent drives the real app or CLI, and forces the failure paths too.'],
    ['Review', false, 'Independent subagents, one lens each. Every finding gets resolved, and any fix goes back through the loop.'],
    ['Manual test', true, 'The agent writes the steps and the expected results. You run them.'],
    ['Commit', true, 'Only after you confirm. Keep this step for yourself if you prefer.'],
    ['Close', true, 'When you say so, the work is archived with its plan, reviews and test records.']
  ];
  var rail = document.getElementById('rail');
  var tag = document.getElementById('stage-tag');
  var title = document.getElementById('stage-title');
  var text = document.getElementById('stage-text');
  var card = document.getElementById('stage-card');
  var current = 0, timer = null, held = false;

  STAGES.forEach(function (s, i) {
    var li = document.createElement('li');
    var b = document.createElement('button');
    b.type = 'button';
    b.innerHTML = '<i>' + (i + 1) + '</i><span></span>';
    b.querySelector('span').textContent = s[0];
    if (s[1]) b.className = 'you';
    b.addEventListener('click', function () { held = true; clearTimeout(timer); show(i); });
    li.appendChild(b);
    rail.appendChild(li);
  });

  function show(i) {
    current = i;
    var items = rail.querySelectorAll('button');
    items.forEach(function (b, k) {
      b.classList.toggle('on', k === i);
      b.classList.toggle('done', k < i);
    });
    title.textContent = STAGES[i][0];
    text.textContent = STAGES[i][2];
    tag.textContent = STAGES[i][1] ? 'Waits for you' : 'The agent works';
    card.classList.toggle('you', STAGES[i][1]);
    rail.style.setProperty('--progress', i / (STAGES.length - 1));
    if (!held && !calm) timer = setTimeout(function () { show((i + 1) % STAGES.length); }, STAGES[i][1] ? 3200 : 1900);
  }
  show(0);

  // The replay opens on an empty screen, so the hero starts a few seconds in.
  var hero = document.querySelector('.term video');
  if (hero) hero.addEventListener('loadedmetadata', function () { hero.currentTime = 6; }, { once: true });

  // The before and after slider.
  var split = document.getElementById('split');
  var before = document.getElementById('before');
  var handle = document.getElementById('handle');
  function move() {
    before.style.clipPath = 'inset(0 ' + (100 - split.value) + '% 0 0)';
    handle.style.left = split.value + '%';
  }
  split.addEventListener('input', move);
  move();

  // Sections rise in once, and the counters run when they come into view.
  function count(el) {
    var to = Number(el.dataset.count), from = Number(el.dataset.from || 0), unit = el.dataset.unit || '';
    if (calm) return;
    var start = performance.now();
    (function step(now) {
      var p = Math.min((now - start) / 1100, 1);
      el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3))) + unit;
      if (p < 1) requestAnimationFrame(step);
    })(start);
  }
  if ('IntersectionObserver' in window && !calm) {
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add('in');
        e.target.querySelectorAll('[data-count]').forEach(count);
        seen.unobserve(e.target);
      });
    }, { threshold: 0.2 });
    document.querySelectorAll('.reveal').forEach(function (el) {
      el.classList.add('pre');
      seen.observe(el);
    });
  }
})();
