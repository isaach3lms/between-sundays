// ---------------------------------------------------------------- mobile nav
(function () {
  var toggle = document.querySelector('.nav__toggle');
  var nav = document.getElementById('nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', function () {
    var open = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.textContent = open ? 'Close' : 'Menu';
  });

  nav.addEventListener('click', function (e) {
    if (e.target.tagName === 'A' && nav.classList.contains('is-open')) {
      nav.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = 'Menu';
    }
  });
})();

// ------------------------------------------------------------- hero rotator
// Cycles "Discipleship is ___" and the field it maps to in the system.
(function () {
  var rotator = document.getElementById('rotator');
  var field = document.getElementById('rotator-field');
  if (!rotator || !window.BS_PHRASES || window.BS_PHRASES.length < 2) return;

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (reduced.matches) return;

  var phrases = window.BS_PHRASES;
  var index = 0;
  var current = rotator.querySelector('.rotator__item');
  var HOLD = 2600;

  // Reserve the height of the tallest phrase so the hero never shifts.
  function lockHeight() {
    var probe = document.createElement('span');
    probe.className = 'rotator__item is-active';
    probe.style.visibility = 'hidden';
    probe.style.position = 'relative';
    rotator.appendChild(probe);
    var tallest = 0;
    for (var i = 0; i < phrases.length; i++) {
      probe.textContent = phrases[i][0];
      tallest = Math.max(tallest, probe.offsetHeight);
    }
    rotator.removeChild(probe);
    if (tallest) rotator.style.minHeight = tallest + 'px';
  }

  lockHeight();
  window.addEventListener('resize', function () {
    rotator.style.minHeight = '';
    lockHeight();
  });

  function next() {
    index = (index + 1) % phrases.length;

    var incoming = document.createElement('span');
    incoming.className = 'rotator__item';
    incoming.textContent = phrases[index][0];
    rotator.appendChild(incoming);

    // Force layout so the transition runs from the start state.
    void incoming.offsetWidth;

    current.classList.remove('is-active');
    current.classList.add('is-leaving');
    incoming.classList.add('is-active');

    if (field) {
      field.classList.add('is-swapping');
      window.setTimeout(function () {
        field.textContent = phrases[index][1];
        field.classList.remove('is-swapping');
      }, 280);
    }

    var leaving = current;
    current = incoming;
    window.setTimeout(function () {
      if (leaving && leaving.parentNode) leaving.parentNode.removeChild(leaving);
    }, 600);
  }

  var timer = window.setInterval(next, HOLD);

  // Pause while the tab is hidden so the sequence is not mid-cycle on return.
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      window.clearInterval(timer);
    } else {
      timer = window.setInterval(next, HOLD);
    }
  });
})();
