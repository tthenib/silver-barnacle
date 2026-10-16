// Mobile navigation
const toggle = document.querySelector('.nav-toggle');
const nav = document.getElementById('site-nav');

if (toggle && nav) {
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    nav.classList.toggle('open', !open);
  });

  nav.addEventListener('click', (e) => {
    if (e.target.closest('a')) {
      toggle.setAttribute('aria-expanded', 'false');
      nav.classList.remove('open');
    }
  });
}

// Footer year
const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

// Quote form: validate, then submit to Formspree without leaving the page
const form = document.querySelector('.quote-form');

if (form) {
  const status = form.querySelector('.form-status');
  const button = form.querySelector('button[type="submit"]');

  const setStatus = (text, type) => {
    status.textContent = text;
    status.className = 'form-status' + (type ? ' ' + type : '');
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const fields = [...form.querySelectorAll('[required]')];
    fields.forEach((f) => f.classList.toggle('invalid', !f.checkValidity()));
    const firstInvalid = fields.find((f) => !f.checkValidity());

    if (firstInvalid) {
      setStatus(
        firstInvalid.id === 'consent'
          ? 'Please tick the box so we can contact you about your quote.'
          : 'Please fill in the highlighted fields.',
        'error'
      );
      firstInvalid.focus();
      return;
    }

    if (form.action.includes('YOUR_FORM_ID')) {
      setStatus('The form isn’t connected yet. Please call or email us instead.', 'error');
      return;
    }

    button.disabled = true;
    setStatus('Sending…');

    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error(res.statusText);
      form.reset();
      setStatus('Thanks! We’ve got your request and will be in touch soon.', 'success');
    } catch {
      setStatus('Something went wrong sending your request. Please try again or give us a call.', 'error');
    } finally {
      button.disabled = false;
    }
  });

  form.addEventListener('input', (e) => {
    if (e.target.classList.contains('invalid') && e.target.checkValidity()) {
      e.target.classList.remove('invalid');
    }
  });
}
