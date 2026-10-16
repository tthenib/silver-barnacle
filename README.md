# Acer Gardening website

A static one-page website for Acer Gardening, a garden maintenance and landscaping business. It's plain HTML, CSS and JavaScript with no build step.

## Files

- `index.html`: home page (services, how it works, areas, FAQ, quote form)
- `privacy.html`: privacy notice linked from the quote form
- `styles.css`: all styles. Colours and fonts are defined at the top as CSS variables.
- `script.js`: mobile menu and quote form submission
- `assets/leaf.svg`: acer leaf logo and favicon

## Before going live

Search for `TODO` in the HTML files and replace the placeholders:

1. **Contact details**: phone, email and opening hours (`index.html` and `privacy.html`).
2. **Areas covered**: the list of towns in `index.html`.
3. **Quote form**: create a free form at [formspree.io](https://formspree.io) and replace `YOUR_FORM_ID` in the form's `action`. Until you do, the form shows a message asking visitors to call or email.
4. **Privacy notice**: check that it matches how you handle enquiries.

## Preview locally

```sh
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Hosting

Any static host works. On GitHub Pages: Settings → Pages → deploy from the `main` branch, root folder.
