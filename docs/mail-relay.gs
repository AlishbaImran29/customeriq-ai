// CustomerIQ AI mail relay: sends the sign-up code from YOUR own Gmail account.
// Paste this whole file into a new project at https://script.google.com, change SECRET, then
// deploy it as a Web app (see "Email codes" in docs/DEPLOY.md).

// Choose your own secret: a few random words with no spaces. It must be the same as the
// MAIL_WEBHOOK_SECRET variable on your API. Never share it or commit it to GitHub.
const SECRET = "PUT-YOUR-OWN-LONG-SECRET-HERE";

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    if (data.secret !== SECRET) return reply({ ok: false, error: "forbidden" });
    MailApp.sendEmail({
      to: data.to,
      subject: data.subject,
      body: data.text,
      htmlBody: data.html,
      name: data.name || "CustomerIQ AI",
    });
    return reply({ ok: true });
  } catch (err) {
    return reply({ ok: false, error: "failed" });
  }
}

// Opening the web app address in a browser shows this line, so you can check it is deployed.
function doGet() {
  return reply({ ok: true, service: "CustomerIQ mail relay" });
}

// Run this once from the editor (Run button) so Google asks you to allow sending email.
function authorize() {
  Logger.log("Emails you can still send today: " + MailApp.getRemainingDailyQuota());
}

function reply(object) {
  return ContentService.createTextOutput(JSON.stringify(object)).setMimeType(ContentService.MimeType.JSON);
}
