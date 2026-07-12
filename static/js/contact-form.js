// Progressive enhancement for the contact form (content/pages/contact/*).
//
// Without JS the form still works: a plain POST to Web3Forms, which then
// redirects to the URL in the hidden `redirect` field (the contact-received
// page in the form's language). With JS we submit via fetch and confirm
// inline instead, so the visitor never leaves the page — and the back
// button can't resurrect a filled-in form after a successful send.
//
// The success/error wording lives on the <form> as data attributes, written
// per language in each translation's body — this module stays language-blind.

const form = document.querySelector("form[data-success]");
const status = document.getElementById("form-status");

function report(kind) {
  status.textContent = form.dataset[kind];
  status.className = `form-status form-status-${kind}`;
  status.hidden = false;
}

if (form && status) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    const body = new FormData(form);
    body.delete("redirect"); // no-JS fallback only; we confirm inline instead

    button.disabled = true;
    status.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body,
        headers: { Accept: "application/json" },
      });
      if (!(await response.json()).success) throw new Error();
      form.reset();
      report("success");
    } catch {
      report("error");
    } finally {
      button.disabled = false;
    }
  });
}
