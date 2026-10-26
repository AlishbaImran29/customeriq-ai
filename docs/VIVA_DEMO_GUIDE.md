# CustomerIQ AI: Viva aur Demo Guide (Roman Urdu)

Ye file aap ke liye hai: teacher ko website kaise dikhani hai, kya bolna hai, kya test karna hai, aur kaun kaun se sawal aa sakte hain.
Ise ek baar poora parh lein, phir demo 2-3 baar khud practise karein.

---

## Hissa 1: Ek line ka pitch (ye yaad kar lein)

> "CustomerIQ AI e-commerce sellers ke liye ek CRM hai, khaas kar Pakistan ke WhatsApp/Instagram aur Cash-on-Delivery sellers ke liye.
> Ye customers ko samajhta hai (segments, churn), orders ka risk batata hai, aur WhatsApp/email se customers ko wapas laata hai.
> Is ka sab se bara usool ye hai: **koi bhi prediction tab dikhayi jati hai jab wo ek simple baseline se behtar ho, warna app khud keh deti hai ke 'prediction available nahi'.**"

Teen cheezein jo har jawab mein ghuma sakti hain: **honest ML (baseline rule)**, **consent-first messaging**, **seller ke liye practical (COD, courier, cash)**.

---

## Hissa 2: Demo se pehle (raat ko ya 1 ghanta pehle)

### Checklist
- [ ] Website kholein: sign in ho jaye (Supabase email/password).
- [ ] Dashboard par data dikhe ("Couldn't load live data" na aaye). Na aaye to Vercel ke API project mein `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL` check karein aur Redeploy karein.
- [ ] Data load ho chuka ho (Hissa 3, step 1).
- [ ] Email Automations page par "Load sample customers and orders" daba chuki hon.
- [ ] Internet ka plan B: apne laptop par local chalayein (niche).
- [ ] Is guide ka Hissa 5 (glossary aur sawal-jawab) ek baar parh len.
- [ ] Report aur slides mein wahi features likhe hon jo ab app mein hain (Hissa 7 dekhein).

### Plan B: laptop par local chalana (internet ya Vercel masla kare to)
1. `D:\CustomerIQ.AI\start-customeriq.bat` par double-click karein.
2. Do black windows khulengi (backend aur website), browser `http://localhost:3001` par khulta hai. Dono windows khuli rakhein.
3. Band karna ho to dono windows band kar dein.
4. Agar "port already in use" aaye to purani windows band karke dobara chalayein.
5. Local par bhi login Supabase se hota hai, to `backend/.env` mein `SUPABASE_URL` aur `SUPABASE_ANON_KEY`, aur `frontend/.env.local` mein `NEXT_PUBLIC_SUPABASE_URL` aur `NEXT_PUBLIC_SUPABASE_ANON_KEY` honi chahiye.
6. Bina backend ke (demo mode) sirf kuch pages sample data dikhate hain; teacher ko ye mat dikhayein, live mode dikhayein.

---

## Hissa 3: Demo script (15-20 minute): shuru se akhir tak

Har step mein **Click** (kya dabana hai), **Bolna** (kya kehna hai).

### 0. Shuruat (1 min)
- **Click:** website kholein, sign in karein.
- **Bolna:** "Ye Next.js ki website hai jo Vercel par hai. Login Supabase Auth se hota hai, hum khud passwords store nahi karte. Pehla account owner banta hai."

### 1. Data import (2 min)
- **Click:** sidebar mein **Import Data**. File `D:\CustomerIQ.AI\data\demo_orders_synthetic.csv` upload karein.
- **Bolna:** "Seller apni orders ki CSV ya Excel ya Shopify export upload karta hai. App har row check karti hai, galat rows reject karke wajah dikhati hai, aur wahi order id dobara aaye to update karti hai, duplicate nahi banati. Ye data synthetic hai (made-up), asli business ka nahi. Model ko asli data par parakhne ke liye humne UCI ka public dataset Online Retail II alag se use kiya."
- Courier shipments, payments aur product sales ki files bhi isi tarah upload hoti hain (Import Data aur Cash Tracker ke pages par cards hain; templates `frontend/public/*_template.csv` mein hain).

### 2. Overview (1 min)
- **Click:** **Overview**.
- **Bolna:** "Yahan 6 KPIs hain: customers, pichle 90 din ka revenue, average CLV, retention, churn risk, growth score. Har number ke saath pichle 90 din se muqabla hai. Growth score humara apna composite hai (revenue growth, retention, customer growth), koi industry standard nahi, aur ye prediction nahi hai."

### 3. Segmentation (2 min)
- **Click:** **Segmentation**.
- **Bolna:** "Ye RFM hai: Recency (aakhri order kab), Frequency (kitni baar), Monetary (kitna kharch). Har customer ko teeno mein 1 se 5 score milta hai (baqi customers ke muqable mein), phir paanch groups: Champions, Loyal, Potential Loyalists, At-Risk, Lost. Segmentation ke liye kam az kam 20 customers chahiye, warna app likhti hai 'need more data', nakli groups nahi banati."

### 4. Churn Prediction (3 min): sab se ahem
- **Click:** **Churn Prediction**, kisi high-risk customer par "Why?" dekhein.
- **Bolna:** "Churn ka matlab hai ke customer agle 90 din mein koi order nahi karega. Model `HistGradientBoostingClassifier` hai (scikit-learn). Train purane data par hota hai aur test **bilkul naye 90 dinon** par, random split nahi, kyun ke random split mein future ka data train mein chala jata aur score jhoota achha aata. 'Why?' mein model ke andar se top 3 wajahen aati hain (jaise 'pichle 120 din se order nahi')."

### 5. Model Report Card (2 min): teacher ko impress karne wala hissa
- **Click:** **Model Report Card**.
- **Bolna:** "Yahan har model ka score uski baseline ke saath hai. Churn ke liye baseline ek simple recency rule hai. Mere test mein Online Retail II (5,852 customers, 36,594 orders, Dec 2009 se Dec 2011) par model ka AUC **0.80** aaya aur simple rule ka **0.76**; Brier score 0.196; test aakhri 90 din par, training 10,208 customer snapshots par. Synthetic data par 0.92 bamuqabla 0.89. Model ne baseline ko haraya, isliye dikhaya gaya. Do aur models (predicted CLV aur revenue forecast) baseline se behtar nahi niklay to maine unhein **hata diya**. Ye project ki imaandari hai."
- Order Risk ke numbers screen se parh kar bolein (wo data aur shipments par depend karte hain).

### 6. Cohorts, Lifetime Value, Revenue (2 min)
- **Cohort Retention:** "Pehle order ke mahine ke hisab se group, aur baad ke mahinon mein kitne percent wapas aaye (heat map)."
- **Lifetime Value:** "Ye ab tak ka kharch hai, predicted nahi."
- **Revenue Intelligence:** "Category, country aur naye vs purane customers se revenue kahan se aa raha hai."

### 7. Recommendations aur AI Assistant (2 min)
- **Recommendations:** "Rules se: kis segment ko kya karna chahiye, kitna audience, kitna purana revenue."
- **AI Business Assistant:** sawal poochein, jaise "Which segment earns the most revenue?". **Bolna:** "AI ko sirf summary figures jate hain, customer ke naam ya email nahi. Jo cheez available nahi, wo AI ko 'notAvailable' bata di jati hai taake wo andaza na lagaye. Har account ke liye sawalon ki limit hai kyun ke har sawal ka paisa lagta hai." (Iske liye `ANTHROPIC_API_KEY` aur credits chahiye; na hon to "AI not configured" dikhega, to ise skip karein ya pehle se test kar lein.)

### 8. Pakistan-specific operations (3 min)
- **Order Risk:** "COD mein order wapas aana bara nuqsan hai. Ye order ke liye wapsi ka risk batata hai (LogisticRegression, explainable), 'Why?' ke saath."
- **Courier Scorecard, Cash Tracker:** "Kaun sa courier kitni jaldi, kitni wapsi; aur courier se paisa kitna aaya, kitna baqi."
- **Real Profit:** "Asli munafa: ad spend, courier charges, wapsi sab ke baad."
- **Meta Ads:** "True ROAS; Meta test mode mein hai, asal mein kuch nahi bhejta jab tak seller on na kare."
- **Season Forecast:** "Product sales ka seasonal andaza, wo bhi tab dikhaya jata hai jab accurate ho."

### 9. Naya order aur COD (2 min)
- **Click:** **Add Order**. Customer, phone, products, amount, "Cash on delivery" chunein.
- **Bolna:** "Order ki entry. Ye order Order Risk mein aur COD confirmation mein aa jata hai."

### 10. Auto Messenger (2 min)
- **Click:** **Messenger Settings, Templates, Consent, COD Confirmation, Announcements, Journeys**.
- **Bolna:** "Teen usool: (1) **consent-first**: jis ne ijazat nahi di use message nahi jata. (2) **Dry-run default**: asal message tab jata hai jab seller khud on kare. (3) **Idempotency**: ek event par ek hi message, dobara nahi. WhatsApp Meta ke official Cloud API se, template seller approve karta hai. Customer 'STOP' likhe to foran band."

### 11. Email Automations (3 min)
- **Click:** **Email Automations**.
- **Bolna aur dikhana:** (a) "Load sample customers and orders" (sample COD order ko confirmation email jati hai), COD table mein status **Pending**. (b) Template previews ke tabs dikhayein: COD, reminder, win-back, new product. (c) Win-back: code `WELCOME10`, value `10%`, "Send win-back emails" (test mode mein sirf log, live mein asal email). Dobara dabayein to "skipped (sent in the last 30 days)". (d) "Announce new product": naam, category bharein, preview, Send. (e) "Send me a test of every email" se apne inbox mein 4 emails dikhayein.
- **COD email ka khaas nukta:** confirm/cancel link signed hai (HMAC + expiry). Link kholne par sirf order dikhta hai, status page ke button dabane par badalta hai, taake mail app ki link-preview galti se confirm na kare.
- **Win-back ka rule:** 60+ din at-risk, 180+ din lost; 30 din mein ek hi baar; unsubscribe link; Brevo free limit 300/din (marketing 270 par ruk jati hai, 30 COD ke liye).

### 12. Workflows, Leads, Returns, Inventory (2 min)
- **Workflows:** "Jab ye ho to wo karo, jaise naya order aaye to task banao. Jobs durable queue mein hain, har run ka log hai."
- **Leads:** "Naye leads, 24 ghante mein jawab na mile to alert."
- **Returns/Refunds, Complaints:** "Return ka process, evidence (photo/video) private storage mein. Refund sirf record hota hai, paisa app se nahi jata."
- **Inventory:** "Order par stock reserve, cancel par wapas."

### 13. Khatma (1 min)
- **Bolna:** "Backend mein 1000+ automated tests hain, frontend ka build/lint/test saaf hai. Limitations ye hain (Hissa 5C ke limitations wale jawab)."

> Tip: har page par agar "Need more data" ya "unavailable" aaye to ghabrayein nahi: **ye app ki khubi hai.** Bolein: "Ye app ka design hai, data kam ho to model chup rehta hai."

---

## Hissa 4: Testing (aap ke liye, main ne ye chala ke dekha hai)

### 4.1 Automated tests (khud chalayein)
| Kya | Command (`D:\CustomerIQ.AI\backend` mein) | Nateeja |
|---|---|---|
| Backend poore tests | `.venv\Scripts\python.exe -m pytest tests -q` | 1000+ tests pass (aakhri run mein koi failure nahi) |
| Sirf emails | `.venv\Scripts\python.exe -m pytest tests\test_email_auto.py -q` | 45 pass |
| Sirf assistant | `.venv\Scripts\python.exe -m pytest tests\test_assistant.py -q` | 31 pass |
| Frontend (`frontend` mein) | `npm.cmd run lint`, `npm.cmd test`, `npm.cmd run build` | lint saaf, 19 tests pass, build "Compiled successfully" |

Ye tests kya parakhte hain: import ki validation, RFM/segments, churn model ka baseline trust-rule, order risk, COD confirmation (YES/NO/timeout), consent aur STOP, quiet hours, idempotency, roles/permissions (viewer likh nahi sakta), Shopify webhook signature, email personalisation (khali value kabhi "None" nahi dikhti), signed links ka expire/forgery, daily limit, unsubscribe, workflows, returns, inventory, aur assistant ki privacy (naam/email AI tak nahi jate). Database tests har baar rolled-back transaction mein chalte hain, asal data nahi badalta.

### 4.2 Manual test checklist (live site par, demo se pehle ek baar)
Har cheez par tick lagayein.

| # | Kya karna hai | Kya hona chahiye |
|---|---|---|
| 1 | Sign in karein | Dashboard khule, "Couldn't load live data" na aaye |
| 2 | Import Data mein `demo_orders_synthetic.csv` upload | "1851 rows" ke qareeb saved, galat rows ki list |
| 3 | Wahi file dobara upload | Duplicate nahi banay (update/skip) |
| 4 | Overview | 6 KPI numbers dikhein |
| 5 | Segmentation | 5 groups, customers ka total 300 |
| 6 | Churn Prediction | Risk levels aur "Why?" dikhe |
| 7 | Model Report Card | Churn "available", model score baseline se zyada |
| 8 | Cohort Retention | Heat map |
| 9 | Add Order (COD) | Order save ho, success message |
| 10 | Email Automations, sample data load | Overview par COD order "Pending" |
| 11 | "Send me a test of every email" | Mode "Live" ho to 4 emails inbox/spam mein |
| 12 | COD email ka Confirm link | Order dikhe, status abhi Pending; button dabane par "Confirmed" |
| 13 | Win-back send, phir dobara | Pehli baar 4 sent; dusri baar "skipped (30 din)" |
| 14 | Announce product, preview, Send | Same-category buyers pehle |
| 15 | Unsubscribe link kholen, phir win-back | Us customer ko dobara email nahi |
| 16 | AI Assistant par ek sawal | Jawab aaye (key ho to) |
| 17 | Sidebar mein ab Launch Studio, Team, Action Log, Duplicate Customers nahi hone chahiyen | Nahi dikhein |
| 18 | Sign out, phir sign in | Theek chale |

### 4.3 Aam masle aur hal
| Masla | Hal |
|---|---|
| "Sign-in is not set up" | Website project mein `NEXT_PUBLIC_SUPABASE_URL` aur `NEXT_PUBLIC_SUPABASE_ANON_KEY`, phir Redeploy |
| "Something went wrong" sign in par | API project mein `SUPABASE_URL` aur `SUPABASE_ANON_KEY`, phir Redeploy |
| "Couldn't load live data" | API project ka `DATABASE_URL`, `DB_SSLMODE=require`; `/api/v1/health` kholein |
| Emails "Test mode" | `BREVO_API_KEY` aur `SENDER_EMAIL` (Brevo mein verified) |
| Confirm/unsubscribe link na bane | `MESSAGING_SECRET` aur `PUBLIC_API_URL` |
| AI Assistant "not configured" | `ANTHROPIC_API_KEY` aur credits |
| Page khali/"Need more data" | Data kam hai; sahi hai, ya zyada data import karein |

---

## Hissa 5: Mushkil lafz (glossary): pehle ye samajh lein

Har lafz ka matlab seedhe alfaz mein, aur ek example. Viva mein ye lafz aayenge; teacher ko example ke saath samjhayen to impression acha parta hai.

### Web aur backend ke lafz
| Lafz | Matlab | Example |
|---|---|---|
| **Frontend** | Wo hissa jo user ko screen par dikhta hai | Website ke pages, buttons, charts (Next.js) |
| **Backend** | Wo hissa jo screen ke peeche kaam karta hai: data nikalna, calculation, rules | "Customer ka churn risk nikalo" (FastAPI) |
| **API** | Frontend aur backend ke beech baat karne ka tareeqa (request/response) | Website backend se poochti hai "customers dikhao", backend JSON mein jawab deta hai |
| **Serverless** | Server hamesha chalta nahi; request aane par chalta hai aur kaam khatam hote hi ruk jata hai | Vercel: jab koi page kholta hai tab hi API code chalta hai |
| **Database (PostgreSQL)** | Data ka mazboot store, tables ki shakal mein | `customers` table, `orders` table |
| **ORM (SQLAlchemy)** | Database ko SQL ke bajaye Python objects se chalana | `Customer(first_name="Ali")` likhna, SQL khud ban jati hai |
| **Migration (Alembic)** | Database ki shakal (tables) mein tabdeeli ka record, version-wise | "0035: email_log table banao" |
| **Environment variable** | Secret ya setting jo code mein nahi, server par rakhi jati hai | `BREVO_API_KEY` Vercel mein, GitHub mein nahi |
| **JSONB** | Postgres ka flexible column jo JSON store kare | Customer ke `tags` ki list |
| **Webhook** | Dusri service khud hamein khabar bheje jab kuch ho | Shopify naya order banne par humari API ko call karta hai |
| **Scheduler / cron** | Waqt ke hisab se kaam chalana | Har kuch der baad "reminder wale orders check karo" |
| **CI/CD** | Code push hote hi khud test aur deploy | GitHub par push, Vercel khud naya version live karta hai |

### Security ke lafz
| Lafz | Matlab | Example |
|---|---|---|
| **Authentication** | "Tum kaun ho?" (login) | Email aur password se sign in (Supabase) |
| **Authorization** | "Tumhein kya karne ki ijazat hai?" | Viewer sirf dekh sakta hai, owner sab kuch kar sakta hai |
| **Token (JWT)** | Login ke baad ka digital parcha jo har request ke saath jata hai | Browser `Authorization: Bearer ...` bhejta hai |
| **HMAC / signed link** | Link mein ek secret se bani mohar (signature) taake koi link jhoota na bana sake | COD email ka Confirm link: order id + expiry + signature |
| **Idempotency** | Ek hi kaam dobara karne par nateeja ek hi rahe, double nahi | Ek order par COD message do baar nahi jata |
| **Rate limit** | Ek user ke sawalon/requests ki had | Assistant: 10 minute mein 15 sawal |
| **CORS / origin check** | Dusri website se hamari API ko chalane se rokna | Kisi aur site ka form hamari API par POST nahi kar sakta |
| **SQL injection** | Hacker input mein SQL daal kar database se khelta hai | Hum parameterised queries (SQLAlchemy) use karte hain, to nahi chalta |
| **XSS** | Hacker page mein script daal deta hai | Jinja2 auto-escape: `<script>` sirf text ban jata hai |

### Business ke lafz
| Lafz | Matlab | Example |
|---|---|---|
| **CRM** | Customer Relationship Management: customers ka data aur un se rabta | Kisne kya khareeda, kab, kaise baat karni hai |
| **COD** | Cash on Delivery: maal aane par paisa | Order aaya, courier ne cash liya |
| **Churn** | Customer ka chhor jana (ab nahi khareed raha) | Ali har mahine leta tha, 4 mahine se nahi aaya |
| **Retention** | Kitne customers wapas khareedte hain | 100 mein se 30 ne dobara order kiya = 30% |
| **CLV (Lifetime Value)** | Ek customer ne poori zindagi mein kitna kharch kiya | Sara ne ab tak 25,000 ka kharch kiya |
| **RFM** | Recency (kab aakhri), Frequency (kitni baar), Monetary (kitna paisa) | 3 din pehle aayi, 12 orders, 80,000 = Champion |
| **Cohort** | Ek hi waqt par shuru hone wale customers ka group | "Jan 2025 mein pehla order karne walay" |
| **ROAS** | Ad par lagaye 1 rupay se kitni sale aayi | 10,000 ad spend, 40,000 sale = ROAS 4 |
| **Consent (opt-in)** | Customer ki ijazat ke message bheje jayen | Customer ne "haan" kaha to hi marketing message |
| **Opt-out / STOP** | Customer ka kehna "ab mat bhejo" | STOP likha to hamesha ke liye band |

### Machine Learning ke lafz
| Lafz | Matlab | Example |
|---|---|---|
| **Model** | Data se seekha hua formula jo andaza lagata hai | "Is customer ka 90 din mein na lautne ka chance 70%" |
| **Feature** | Wo cheez jo model dekhta hai | Aakhri order ko kitne din hue, kitne orders |
| **Train / Test** | Train: sikhana. Test: imtihan. Alag data par | Purane data se seekha, naye 90 din par imtihan |
| **Time-based split** | Test hamesha train ke baad ka waqt ho | Dec 2010 tak train, Sep-Dec 2011 par test |
| **Data leakage** | Test ka jawab train mein chala jana, score jhoota achha | Mustaqbil ke orders se mustaqbil ka andaza |
| **Baseline** | Sab se aasan rule jise model ko harana hai | "Jis ka aakhri order jitna purana, utna risk" |
| **AUC (ROC-AUC)** | 0.5 = sikke ka toss, 1.0 = perfect. Kitna sahi high-risk ko low-risk se alag karta hai | 0.80: 100 mein 80 jodiyon mein sahi tarteeb |
| **Brier score** | Probability kitni sahi hai (kam behtar) | 0.196 |
| **Precision (top 10%)** | Sab se risky 10% orders mein se kitne sach mein risky nikle | 100 risky bataye, 60 sach mein wapas aaye = 60% |
| **Imbalanced data** | Ek qisam bohat kam, doosri bohat zyada | Zyada orders theek, thore wapas hote hain |
| **Overfitting** | Model data ratta maar le, naye data par fail | Imtihan ke sawal rat liye, naye sawal par fail |
| **HistGradientBoosting** | Kai chhote decision trees mil kar ek mazboot model | Churn model |
| **Logistic Regression** | Sada, samajhne mein asaan model jis ka har feature ek weight | Order risk model |
| **Ridge regression** | Seedhi line fit jis mein extra penalty taake overfit na ho | Season forecast |
| **Explainability ("Why?")** | Model ka faisla wajah ke saath | "Risk isliye ke 120 din se order nahi" |

### Testing ke lafz
| Lafz | Matlab | Example |
|---|---|---|
| **Unit test** | Ek chhoti cheez ko akela parakhna | `first_name("MARY-ANNE")` = "Mary-Anne" |
| **Integration / API test** | Pori request ko database ke saath parakhna | `/email/cod/token` par POST se status confirmed |
| **Dry-run** | Sab kuch chala kar dekhna magar asal mein kuch bhejna nahi | Message log hota hai, customer ko nahi jata |

---

## Hissa 5B: Mumkin sawal aur jawab (examples ke saath)

> Format: **Sawal** → **Jawab** → *Example/Nukta*.

### A. Project
**1. Masla kya hai? Ye project kyun?**
Chhote online sellers ke paas data hota hai magar samajh nahi hoti: kaun customer chhor raha hai, kaun si COD order wapas aayegi, kab kis ko message karna hai. Bare CRM mehnge hain aur Pakistan ke COD, courier aur WhatsApp ko nahi samajhte.
*Example:* Ek seller ke 500 customers hain. App batati hai "in 40 ne 4 mahine se kuch nahi khareeda, un mein se 15 pichle saal ke Champions the", seller un ko win-back email bhejta hai.

**2. Is mein naya kya hai?**
(1) **Trust rule**: prediction sirf baseline se behtar hone par. (2) COD/courier/cash ka asli kaam. (3) Consent-first messaging. (4) "Why?" explanations.

**3. Competitors se farq?**
HubSpot, Klaviyo, Zoho mehnge, English-first, COD aur courier nahi. Hum local workflow aur honest ML dete hain.

**4. Data kahan se?**
Seller ki CSV/Excel, Shopify export/webhook, Add Order form. Testing: synthetic data aur UCI Online Retail II (public, CC BY 4.0, credit zaruri).

### B. Technologies
**5. Next.js aur React kyun?**
Page jaldi load hota hai (server rendering), routing file se khud banti hai, Vercel par deploy asaan. TypeScript galtiyan build se pehle pakar leta hai.
*Example:* `app/churn/page.tsx` bana dein to `/churn` page khud ban jata hai.

**6. FastAPI kyun, Django/Flask kyun nahi?**
FastAPI tez hai, Pydantic se request khud validate hoti hai, aur `/docs` mein documentation khud ban jati hai. Python hai to scikit-learn seedha chalta hai.
*Example:* phone ki jagah text bhej do to API khud "422 validation error" deti hai.

**7. PostgreSQL kyun?**
Data relational hai (customer → order → shipment → refund) aur rules chahiye. *Example:* order ki value negative nahi ho sakti, database khud rok deta hai.

**8. Supabase kyun?**
Hosted Postgres + Auth + private storage ek jagah. Passwords hum store nahi karte, ye khatra kam karta hai.

**9. Alembic migration kya?**
Database ka version control. *Example:* naya feature aaya to `0035` migration se `email_log` table banti hai; dobara chalane par duplicate nahi banti.

**10. scikit-learn aur deep learning?**
Data chhota/darmiyana hai aur seller ko wajah chahiye. Gradient boosting aur logistic regression is size par achhe aur explainable hain. Deep learning ko bahut data chahiye.

**11. Brevo, WhatsApp Cloud API, Claude/OpenAI?**
Brevo: email HTTPS par (Vercel par SMTP nahi chalta), free 300/din. WhatsApp Cloud API: Meta ka official tareeqa. Claude/OpenAI: Assistant aur campaign drafts; `AI_PROVIDER` se badal sakte hain.

**12. Serverless mein background kaam kaise?**
GitHub Actions har kuch der baad ek protected endpoint (`/internal/run-scheduler`, secret ke saath) ko bulata hai. Har pass chhota aur safe hai.
*Example:* reminder pass do baar chale to bhi customer ko ek hi reminder jata hai (idempotency).

**13. Jinja2 kyun?**
Email ka text alag files mein (seller/developer aasani se badle) aur auto-escape se injection nahi.

**14. Tailwind tokens?**
Rang `globals.css` mein ek jagah. *Example:* `--color-accent` badlen to poori site ka blue badal jata hai.

### C. Machine Learning
**15. Churn kaise define kiya?**
Kisi tareekh par dekha: agle 90 din mein order aaya ya nahi. Nahi aaya = churn (label 1).
*Example:* 1 Jan ko Ali ki history dekhi; 1 Jan se 31 Mar tak order nahi to label "churn".

**16. Features kya the?**
Customer ki purani history: recency, frequency, monetary, usual gap, pichle 90 din ke orders. Sab us din tak ki maloomat se (point-in-time).

**17. Data leakage kaise roki?**
Time-based split: purana train, naya test. Features sirf us tareekh tak ke data se.
*Example:* agar 15 Dec ka order train mein ho aur 1 Dec ke churn ka label usi se bane, to model ko jawab pehle se pata hoga, jhoota score.

**18. Accuracy kyun nahi, AUC kyun?**
Churn mein ek class bari hoti hai, accuracy dhokha deti hai. AUC batata hai high-risk ko low-risk se alag karna kitna accha aata hai.
*Example:* 95% customers wapas aate hon to "sab wapas aayenge" kehne wala model 95% accurate hoga par bekar.

**19. Baseline kya, aur kyun?**
Sab se simple rule (aakhri order jitna purana utna risk). Agar mehnat wala model is se behtar nahi to dikhana bekar hai. Humare test mein model 0.80, rule 0.76 (UCI data).

**20. 0.80 kam to nahi?**
Insani behaviour mein shor hota hai. Ahem baat: model simple rule se behtar hai aur test naye, na dekhe hue 90 dinon par hai. Hum score chhupate nahi, Report Card mein dikhate hain.

**21. CLV aur forecast kyun hata diye?**
Dono baseline se behtar nahi niklay Online Retail II par. Trust rule ke mutabiq unhein dikhana ghalat tha. CLV ab "ab tak ka kharch" hai.

**22. "Why?" kaise banti hai?**
Har feature ko typical value se badal kar dekhte hain risk kitna girta hai; sab se zyada girne wale top 3 wajah.
*Example:* "No order for 120 days" sab se bara asar.

**23. Order Risk model?**
Logistic Regression (har feature ka ek weight, explain karna asaan). Label: order wapas/cancel. Time split (naye 25% test). Baseline: customer ki apni purani cancel rate. Metrics: AUC aur top 10% precision.

**24. Season Forecast?**
Eid/Christmas jaise season mein product ki units ka andaza. Baseline: pichle saal usi season ki sales. Model: Ridge regression (pichle do saal + forecast se pehle ke 8 hafton ki sales). Forecast season se 28 din pehle banta hai, test sirf us se pehle ke data se. Model ka error baseline se kam az kam 5% behtar na ho to page "pichle saal ki sales" dikhata hai. Saath mein 80% range.

**25. RFM kaise?**
Har customer ko baqi customers ke muqable mein rank karke 1-5 score (quintile). *Example:* R=5, F=5, M=5 → Champion.

**26. Cold start (kam data)?**
Page likhta hai "need more data" aur wajah. Nakli number kabhi nahi.

### D. Data
**27. Duplicate customer kaise rokte?**
Phone `+923XXXXXXXXX` mein normalise, wahi phone = wahi customer; order id unique.
*Example:* "0300-1234567" aur "+92 300 1234567" ek hi customer.

**28. Import validation?**
Har row check (zaruri columns, tarikh, amount, phone); galat rows ki list wajah ke saath; wahi order id dobara aaye to update.

### E. Messaging aur Email
**29. Consent kaise?**
Consent record nahi to marketing nahi. STOP/unsubscribe par foran opt-out, aur wo hamesha jeet'ta hai. Har tabdeeli ka history record (`consent_events`).

**30. Dry-run?**
Default mein asal message nahi jata, sirf log. Seller khud on karta hai.

**31. Ek message do baar kaise nahi?**
Har event ki unique key (jaise `order:12:cod_confirmation`). Dobara chale to wahi key mil jati hai.

**32. COD email ka link secure kaise?**
Link mein order id, action (confirm/cancel), expiry aur HMAC signature hai. Jhoota link ban nahi sakta. Link kholne se status nahi badalta; page ka button (POST) dabane se badalta hai.
*Example:* Gmail ya antivirus link ko "preview" karne ke liye khole to order galti se confirm nahi hoga.

**33. Personalisation?**
Pehla naam (capitalise, na ho to "Hi there"), order ki tafseel, aakhri product, 3 recommended products. Jo data nahi, wo hissa chhup jata hai.
*Example:* `mary-anne` → "Hi Mary-Anne"; naam khali → "Hi there".

**34. Brevo ki 300/din limit?**
Har email ka log; marketing 270 par ruk jati hai, 30 COD ke liye bachte hain.

### F. Security
**35. Login aur roles?**
Supabase Auth se login; backend har request par token verify karta hai; roles (owner/staff/viewer) ka table server par enforce hota hai.
*Example:* viewer ne `POST /leads` kiya to 403 forbidden, chahe button chhupa na ho.

**36. API keys kahan?**
Sirf server (Vercel env vars). `NEXT_PUBLIC_*` mein sirf public cheezein (Supabase URL, anon key).

**37. AI ko kya jata hai?**
Sirf aggregate figures aur anonymous customer ids; naam, email, phone nahi. Sawal/jawab log nahi hote.

**38. Customer ka data mitana?**
Customer records mein anonymise/delete: naam, email, phone, messages, videos mit jate hain, order figures sahi rehte hain.

### G. Deployment aur Testing
**39. Deploy kaise?**
GitHub push → Vercel do projects (website, API) khud build/deploy. Database migration `migrate_remote.py` se.

**40. Testing kaise?**
Backend ke 1087 automated tests (logic, API, database, security), frontend lint/build/19 tests, aur manual checklist. ML ki testing: naye data par baseline se muqabla. Database tests rolled-back transaction mein, asal data nahi badalta.

---

## Hissa 5C: Phansane wale (counter) sawal aur unka jawab

**Phansne par 4-qadam ka formula:** (1) sawal dohra kar sach maan lein (2) seedha jawab (3) apni limitation imaandari se (4) agla qadam / future work. Kabhi bahas nahi, kabhi jhoot nahi.

**1. "Ye sab libraries ne kiya, aap ne kya kiya?"**
"Libraries tools hain (scikit-learn model deta hai), magar mera kaam: data ki cleaning aur validation, point-in-time features, time-based testing, baseline se muqabla aur trust rule, 'Why?' explanation, consent/idempotency/roles ka logic, aur Pakistan ke COD/courier/cash ka poora workflow. Ye logic humare code mein hai (jaise `predictions.py`, `order_risk_model.py`, `permissions.py`)."

**2. "0.80 AUC to kam hai, 0.5 to random hota hai?"**
"Sahi, random 0.5 hai, to 0.80 kaafi upar hai. Dekhein, simple rule bhi 0.76 deta hai, isliye model ka faida chhota magar sachcha hai, aur naye data par. Behtari ke liye zyada asli seller data aur features chahiye, ye future work hai."

**3. "Synthetic data par test ka kya faida?"**
"Synthetic sirf demo aur code ki durustgi (import, pages, workflows) ke liye hai, ML ki quality ke liye nahi. ML ke liye asli public dataset UCI Online Retail II (5,852 customers) use kiya."

**4. "Model overfit to nahi?"**
"Overfit ka matlab train par achha, naye data par bura. Humara score hi naye, na dekhe hue 90 dinon par hai. Agar overfit hota to wahi score girta aur baseline se haar jata, to app model dikhati hi nahi."

**5. "Random split ya cross-validation kyun nahi?"**
"Customer ka behaviour waqt ke saath hota hai; random split mein future ka data train mein aa jata (leakage). Time-based split asli zindagi jaisa hai: purane se seekho, naye ka andaza lagao."

**6. "Agar model baseline se behtar na ho to feature bekar nahi?"**
"Nahi, wahi to taqat hai. Jhoota predict karne se 'available nahi' kehna behtar hai, kyun ke seller ghalat faisle le sakta hai. Baaqi analytics (RFM, retention, cohort) bina ML ke kaam karti hain."

**7. "Kya ye asli seller par chala?"**
"Abhi nahi. Synthetic aur public data par parakha gaya. Asli seller par pilot future work hai aur main ye saaf bata deta hun."

**8. "Ye code AI ne likha?"**
Imaandari se, disclosure ke mutabiq: "Is project mein AI tools ki madad li gayi, tafseel AI Use Disclosure mein hai. Design, data, aur fesle mere hain, aur main har hissa samjha sakti hun." Phir koi bhi hissa kholen aur samjhayen (jaise `globals.css` ya ek template). **Jo samajh na aaye wo na bolein.**

**9. "Do log ek hi order ek saath confirm/cancel karein to?"**
"Pehla jawab hi chalta hai (status 'pending' se hi badalta hai; baad mein wahi dikhata hai). Order id par unique constraint hai, to data kharab nahi hota."

**10. "Supabase ya Vercel band ho jaye?"**
"Hosted services hain jin ki apni uptime hai. Agar band ho to app nahi chalegi; production mein status monitoring aur backup chahiye (future work). Demo ke liye laptop par local plan B hai."

**11. "1 million customers par?"**
"Honestly, abhi analytics poora data memory mein load karti hai, to bohat bare data par pre-calculated tables (aggregates) aur background jobs chahiye. Humare target (chhote/darmiyane seller) ke liye theek hai."

**12. "WhatsApp asal mein kyun nahi chala?"**
"Meta ke official API ke liye business verification aur message templates ki approval chahiye. Isliye abhi test mode (dry-run) mein hai. Code taiyar hai; keys aur approval milte hi chal jayega."

**13. "Consent ka saboot?"**
"Har tabdeeli `consent_events` table mein (kab, kis source se: checkout tick, import, STOP). Bina record ke marketing nahi jati."

**14. "Pakistan ke data protection / GDPR?"**
"Poori legal compliance ka daawa nahi karte. Ye teen cheezein hain: consent, erase (anonymise/delete) aur data minimisation (AI ko naam/email nahi). Legal review production se pehle zaruri hai."

**15. "Teen mahine mein koi nayi baat aa gayi (concept drift)?"**
"Models naye data par dobara train hote hain jab data badalta hai, aur har dafa dobara baseline se parakhe jate hain."

**16. "AI Assistant ghalat jawab de to?"**
"Usay sirf summary figures aur 'notAvailable' list di jati hai, aur hidayat hai ke bahar ka andaza na lagaye aur jo data mein na ho wo saaf kahe. Phir bhi AI ghalat ho sakta hai, isliye wo 'sahayak' hai, faisla seller ka."

**17. "AI ka kharcha?"**
"Har sawal par paisa lagta hai: isliye rate limit (15 sawal/10 minute), cache, aur chhota summary."

**18. "Naya feature kaise add karte?"**
"Model (table) → migration → service (logic) → API endpoint → page → test. Jaise Email Automations ke liye: `email_auto.py` model, migration 0035, service, API, page."

**19. "Ek line badal kar dikhayein."**
Taiyar rahein: rang badalna (`frontend/app/globals.css` mein `--color-accent`), ya email ka text badalna (`backend/app/email_templates/winback.html`). Dono jagah pehle se dekh lein.

**20. "Microservices kyun nahi?"**
"Chhoti team aur chhota project; do hisse (website, API) kaafi hain. Microservices se kharcha aur pechidgi barhti."

**21. "Real-time hai?"**
"Analytics request par calculate hoti hai aur messaging scheduler se batches mein; 'real-time streaming' nahi."

**22. "Spam ka khatra?"**
"Consent, quiet hours, weekly marketing cap, 30 din mein ek win-back, unsubscribe link, aur dry-run default."

**23. "Dataset ka licence?"**
"UCI Online Retail II, CC BY 4.0: credit dena zaruri hai, humare report mein reference hai."

**24. "Test coverage kitni?"**
"Number ke bajaye bataein ke kya kya covered hai: 1087 tests jo logic, API, database, security aur privacy cover karte hain. Coverage percent maine measure nahi kiya."

**25. Agar bilkul jawab na aaye:**
"Ye hissa mujhe poori tarah yaad nahi aa raha, main code mein dekh kar abhi bata sakti hun" (aur wahi file kholen), ya "ye main dobara parh kar mukammal jawab de dun gi." Jhoot se behtar hai.

**26. "Aap ki limitations aur future work kya hain?"** (ye sawal lagbhag zaroor aata hai)
*Limitations:* (1) asli seller par pilot nahi hua, (2) chhote data par models kamzor ya "unavailable", (3) WhatsApp abhi Meta test mode/dry-run mein, (4) refund sirf record hota hai, paisa app se nahi jata, (5) sirf ek owner account (Team page nahi), (6) sirf English aur £, (7) Shopify API sync nahi, sirf export/webhook, (8) bohat bare data ke liye pre-calculated tables chahiye.
*Future work:* asli sellers par pilot, WooCommerce, Urdu interface, zyada data par behtar models, multiple team members, background workers, monitoring aur backups.

---

## Hissa 6: Demo ke waqt ke usool
1. Pehle live mode dikhayein, plan B sirf zarurat par.
2. Koi page "unavailable" dikhaye to khud wajah parh kar bolein.
3. Aisa kuch mat bolein jo aap ne test nahi kiya.
4. Wahi numbers bolein jo screen par hain (churn: 0.80 vs 0.76 UCI par; screen ke numbers is se thore mukhtalif ho sakte hain agar data alag ho).
5. Teacher ko khud click karne dein, bhi acha lagta hai.

## Hissa 7: Report aur slides mein update (zaroori)
Ye features ab app mein **nahi** hain: Launch Studio (trend finder, vendor book, competitor board, creatives, profit check), WhatsApp chat import, Team page, Duplicate Customers, Action Log page, health score, predicted CLV, revenue forecast, revenue by channel, Urdu/multi-currency. Report/slides/screenshots mein ye likhe hon to hata dein, warna teacher poochega "ye kahan hai?".
Ye features **naye** hain, report mein shamil karein: Email Automations (COD confirm, win-back, new product), AI Assistant (dobara), CRM-style light theme.
