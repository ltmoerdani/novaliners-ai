/* Demo data (Dimas scenario) — fixtures for ?dev=1 demo mode. Copy is verbatim from prototype v9. */
const STEP_STATUS = { COMPLETED: 'COMPLETED', CURRENT: 'CURRENT', UPCOMING: 'UPCOMING' };
/* Steps are tasks, not calendar slots: `day` is only when the plan suggests doing it. A step is ready as soon as the
   steps it `needs` are done (default: the step before it), so two steps can be ready on the same day and be done in
   either order. The report step is ready once every other step is done. */
const CYCLE1_STEPS = [
  { num: 1, label: 'Write a one-page offer', day: 1, dayLabel: 'Day 1–2', mapLabel: 'Offer', needs: [] },
  { num: 2, label: 'Send it to the 2 who asked', day: 3, dayLabel: 'Day 3', mapLabel: 'Send', needs: [1], sent: true },
  { num: 3, label: 'Follow up, book a call', day: 4, dayLabel: 'Day 4–5', mapLabel: 'Follow-up', needs: [2] },
  { num: 4, label: 'Send to 5 more people you know', day: 6, dayLabel: 'Day 6', mapLabel: 'Outreach', needs: [1] },
  { num: 5, label: 'Report what happened', day: 7, dayLabel: 'Day 7', mapLabel: 'Check-in', report: true }
];

/* Plans for Cycle 2 onward: one 5-step plan per path chosen at a check-in.
   Each step carries the copy the Today screen shows for it. */
let GOAL_DAY = 90;   // horizon of the current map in days (live: parsed from the goal)
function cycleDays(cycle) {
  const start = (cycle - 1) * 7 + 1;
  const d = n => Math.min(start + n, GOAL_DAY);
  const range = (a, b) => (d(a) === d(b) ? `Day ${d(a)}` : `Day ${d(a)}–${d(b)}`);
  return [
    { day: d(0), dayLabel: `Day ${d(0)}` },
    { day: d(1), dayLabel: range(1, 2) },
    { day: d(3), dayLabel: range(3, 4) },
    { day: d(5), dayLabel: `Day ${d(5)}` },
    { day: d(6), dayLabel: `Day ${d(6)}` }
  ];
}
const CYCLE2_REPORT_STEP = {
  label: "Report this week's results", mapLabel: 'Check-in', report: true,
  tag: 'Day 14 · check-in',
  title: 'Report what happened this week.',
  desc: 'Tell us who replied, who you spoke to, and whether anyone paid. Your map updates from there.',
  box: () => renderDoneBox('All 5 steps done', 'Time for your check-in: how many people replied, how many calls you had, and whether anyone paid.')
};
/* The diagnosis of the map (Dimas), shown on the Diagnosis screen. Cycle 1 repeats the reveal (screen 03); later cycles restate the
   constraint per plan (CYCLE2_PLANS[*].diagnosis). Ads stay on hold in every cycle. */
const DEMO_DIAGNOSIS = {
  confidence: 'High confidence', verdict: 'GO SMALL', line: "Move, but don't spend money yet.",
  headline: "Your expertise isn't the problem. It just isn't packaged as an offer yet.",
  summary: ['You left your job and you are starting from Rp0 a month, with a goal of Rp30M in 90 days. Behind you are 2 paid projects worth Rp12.5M in total, and 2 people who said, "Tell us when you start."', 'What stands out: the skill is there and two people are waiting, but there is nothing written for them to say yes to. We do not know yet whether either would buy. So the first step is small: put the offer on one page and send it.'],
  blockHead: 'You have no written offer to send.',
  blockRest: "Two people asked to hear from you when you start, but there's nothing specific for them to say yes to.",
  chips: ['Based on: 2 paid projects', '2 contacts asked'],
  why: [['You told us', '2 contacts asked to hear from you when you start.'], ['You told us', '2 paid projects behind you, Rp12.5M in total.'], ['Still unknown', 'Whether either contact would say yes to a written offer.']],
  stopHead: "Don't rent the office.",
  stopRest: "No client has asked where you work. Also on hold: LinkedIn ads and registering a company.",
  stopPill: 'Keeps Rp20M in your pocket',
  stopLaterHead: "Don't put Rp10M into LinkedIn ads.",
  stopLaterRest: "You don't have an offer that sells on its own yet. A capped Rp2M test is the most to risk."
};
const CYCLE2_PLANS = {
  audit: {
    title: 'Fixed-price brand audit',
    pill: '<span class="status-pill open">OPEN</span>',
    success: 'A second client signs at Rp15M, so you know you can sell this offer again without a custom proposal.',
  diagnosis: { summary: ['Sari paid for a brand audit made just for her. That shows people will pay you for this work.', 'What we do not know yet is whether it sells again without a custom proposal. A second client at a fixed price would show you can repeat it. That is what this week is for.'], headline: 'Your audit has sold once. Now it has to sell again without a custom proposal.', blockHead: 'One audit is a story, not yet an offer.', blockRest: 'Sari paid for a custom audit. A second client at a fixed price shows you can repeat it.' },
    steps: [
      {
        label: 'Define the standard package', mapLabel: 'Package',
        tag: 'TODAY · UNDER 45 MINUTES',
        title: 'Write down what your fixed-price 2-week brand audit includes.',
        desc: 'Turn the audit you just did for Sari into a standard 14-day package at Rp15M, ready for the contact who asked about your price.',
        box: () => renderListBox('What the package includes', 'Fixed 2-Week Brand Audit Package (Rp15M):', [
          '<strong>Part 1:</strong> A review of where the brand sells and what makes it stand out (15 slides)',
          '<strong>Part 2:</strong> A comparison with 3 main competitors, showing gaps the brand can fill',
          '<strong>Part 3:</strong> A 90-day action plan, plus a 60-minute session to walk the team through it'
        ])
      },
      {
        label: 'Send it to the person who asked about price', mapLabel: 'Send', sent: true,
        tag: 'DAY 9–10 · UNDER 20 MINUTES',
        title: 'Send the package to the contact who asked about your price.',
        desc: "They asked first, so this isn't a cold pitch. Keep the message short and let the one-page package do the talking.",
        box: isId => renderMsgBox('WhatsApp message, ready to send',
          "Hi [Name], you asked what a brand audit from me would cost. Here it is: a fixed 2-week audit for Rp15 million. I've attached a one-page summary of what's included.\n\nIf it looks useful, could we have a 20-minute call this week to see if it fits your brand?",
          'Halo [Nama], kemarin sempat tanya biaya audit brand dari saya. Ini detailnya: audit 2 minggu dengan harga tetap Rp15 juta. Ringkasan 1 halamannya saya lampirkan.\n\nKalau cocok, boleh kita ngobrol 20 menit minggu ini untuk lihat apakah pas dengan brand kamu?', isId)
      },
      {
        label: 'Call to go over the details', mapLabel: 'Call',
        tag: 'DAY 11–12 · 20-MINUTE CALL',
        title: 'Have a 20-minute call to go over the details.',
        desc: 'Your goal on this call is to understand what they need, not to push. Use these 4 questions, then agree on a next step.',
        box: () => renderListBox('Your call plan', '4 questions to ask:', [
          'What made you ask about an audit now?',
          'What would you want to be different in 3 months?',
          'Who else needs to agree before you start?',
          'Would a start date in the next 2 weeks work for you?'
        ], true)
      },
      {
        label: 'Reach out to 3 brands you want to work with', mapLabel: 'Outreach', sent: true, needs: [1],
        tag: 'DAY 13 · UNDER 30 MINUTES',
        title: "Send the package to 3 brands you'd like to work with.",
        desc: 'Pick 3 brands you already know something about. Mention one specific thing you noticed, so the message feels personal.',
        box: isId => renderMsgBox('Message to a brand you want to work with',
          "Hi [Name], I've been following [Brand] for a while and noticed [one thing you saw]. I now run a fixed-price 2-week brand audit that helps brands like yours see what to fix first.\n\nCould I send you the one-page summary?",
          'Halo [Nama], saya sudah cukup lama mengikuti [Brand] dan memperhatikan [satu hal yang kamu lihat]. Sekarang saya punya layanan audit brand 2 minggu dengan harga tetap, untuk membantu brand seperti [Brand] tahu apa yang perlu dibenahi dulu.\n\nBoleh saya kirim ringkasan 1 halamannya?', isId)
      },
      CYCLE2_REPORT_STEP
    ]
  },
  warm_starter: {
    title: 'Advising people you know · Smaller offer',
    pill: '<span class="status-pill open">OPEN · ADJUSTED</span>',
    success: 'At least 1 of the 2 says yes to the smaller version.',
  diagnosis: { summary: ['You spoke with two people about the full offer. Both were interested, and neither said yes.', 'It looks like the first step felt too big for them. A smaller 2-week version costs them less to try. This week is about making it easy to say yes.'], headline: 'The full offer felt too big to say yes to. A smaller first step should be easier.', blockHead: 'The first step felt too big.', blockRest: 'Both calls were interested but did not commit. A smaller 2-week version lowers the risk for them.' },
    steps: [
      {
        label: 'Make a smaller 2-week version', mapLabel: 'Resize',
        tag: 'TODAY · UNDER 45 MINUTES',
        title: 'Make a smaller 2-week version of your offer for Rp7.5M.',
        desc: 'They asked for a smaller start, not a lower price. Put together a short 14-day package.',
        box: () => renderListBox('What the package includes', '2-Week Starter Audit (Rp7.5M):', [
          'One 90-minute working session',
          'A short report on the 3 biggest problems',
          'A ranked action plan for the next 3 months'
        ])
      },
      {
        label: 'Send it to the 2 people you called', mapLabel: 'Send', sent: true,
        tag: 'DAY 9–10 · UNDER 20 MINUTES',
        title: 'Send the smaller version to the 2 people you called.',
        desc: "Remind them it's what they asked for. That makes it easy to say yes.",
        box: isId => renderMsgBox('WhatsApp message, ready to send',
          'Hi [Name], thanks again for the call. You asked if there was a smaller way to start, so I put one together: a 2-week version for Rp7.5 million. The one-page summary is attached.\n\nWould this work as a first step for you?',
          'Halo [Nama], terima kasih lagi untuk obrolan kemarin. Kamu sempat tanya apakah ada cara mulai yang lebih kecil, jadi saya siapkan versi 2 minggu seharga Rp7,5 juta. Ringkasan 1 halamannya saya lampirkan.\n\nApakah ini cocok sebagai langkah pertama?', isId)
      },
      {
        label: 'Follow up and answer questions', mapLabel: 'Follow-up', sent: true,
        tag: 'DAY 11–12 · UNDER 15 MINUTES',
        title: 'Follow up and answer their questions.',
        desc: "If they haven't replied, a short and friendly nudge is enough. Don't lower the price.",
        box: isId => renderMsgBox('Follow-up WhatsApp message',
          'Hi [Name], just checking in on the 2-week option I sent. Happy to answer any questions. If it helps, we could start as early as next week.',
          'Halo [Nama], mau cek soal pilihan 2 minggu yang saya kirim kemarin. Kalau ada pertanyaan, silakan saja. Kalau cocok, kita bisa mulai paling cepat minggu depan.', isId)
      },
      {
        label: 'Book a start date with whoever says yes', mapLabel: 'Kickoff',
        tag: 'DAY 13 · UNDER 20 MINUTES',
        title: 'Book a start date with whoever says yes.',
        desc: 'Once someone says yes, lock in the details so the work actually starts.',
        box: () => renderListBox('Before you start', 'Tick these off with your new client:', [
          'Agree on a start date',
          'Send a simple invoice for Rp7.5M (asking for 50% upfront is fine)',
          'Schedule the 90-minute working session',
          'Ask for any data or files you need'
        ], true)
      },
      CYCLE2_REPORT_STEP
    ]
  },
  warm_retest: {
    title: 'Advising people you know · Trying again',
    pill: '<span class="status-pill open">OPEN · TRYING AGAIN</span>',
    success: '1 conversation booked.',
  diagnosis: { summary: ['You sent six messages and got no replies. That is not the same as six people saying no.', 'The messages were probably too long to answer. A short ask with a quick call gives people an easy way to reply. This week we try that and see.'], headline: 'Your last message got no replies. A shorter ask and a quick call may fix that.', blockHead: 'The message was probably too long.', blockRest: 'Six messages, no replies. A short call gives people an easier way to answer.' },
    steps: [
      {
        label: 'Call the 2 contacts who asked', mapLabel: 'Call',
        tag: 'TODAY · UNDER 20 MINUTES',
        title: 'Call the 2 contacts who asked. 10 minutes each, nothing attached.',
        desc: "A quick call feels more personal than another message. You're not selling yet, just catching up.",
        box: () => renderQuoteBox('What to say on the 10-minute call:', '“Hi, I sent you a short summary of my offer the other day. So I can make it a better fit, can I ask one quick thing: what is the most urgent challenge for your brand right now?”')
      },
      {
        label: 'Ask what would make it worth their time', mapLabel: 'Ask',
        tag: 'DAY 9–10 · During the call',
        title: 'Ask one question: what would make it worth their time?',
        desc: 'Listen more than you talk. Their answer tells you how to shape the offer.',
        box: () => renderQuoteBox('The one question:', '“What would make a 20-minute chat about your brand worth your time?”', 'Then stay quiet and let them answer.')
      },
      {
        label: 'Write down what they said', mapLabel: 'Notes',
        tag: 'DAY 11–12 · UNDER 15 MINUTES',
        title: 'Write down what they said, word for word.',
        desc: "Their exact words are the best material for your next offer. Don't tidy them up.",
        box: () => renderListBox('Your notes', 'Fill these in right after each call:', [
          'Contact 1 said: “…”',
          'Contact 2 said: “…”',
          'What surprised you?'
        ])
      },
      {
        label: 'Send a short follow-up', mapLabel: 'Follow-up', sent: true,
        tag: 'DAY 13 · UNDER 15 MINUTES',
        title: 'Send a short follow-up based on what they told you.',
        desc: 'Show them you listened. Use their words and suggest one small next step.',
        box: isId => renderMsgBox('Follow-up WhatsApp message',
          'Hi [Name], thanks for the chat. You mentioned [what they said]. I could help with exactly that in a short 2-week project. Would it be worth a 20-minute call next week?',
          'Halo [Nama], terima kasih untuk obrolannya. Kamu sempat bilang [yang dia katakan]. Saya bisa bantu persis di bagian itu lewat proyek singkat 2 minggu. Boleh kita ngobrol 20 menit minggu depan?', isId)
      },
      CYCLE2_REPORT_STEP
    ]
  },
  warm: {
    title: 'Advising people you know',
    pill: '<span class="status-pill open">OPEN</span>',
    success: 'At least 2 more people ask what working with you would cost.',
  diagnosis: { summary: ['The people who know you have already heard the offer, and your first clients came from them.', 'That circle is running out, so new clients have to come from further away. This week is about reaching people who do not know you yet.'], headline: "Your offer sells to people who know you. Now it has to reach people who don't.", blockHead: 'Your network is running out.', blockRest: 'The people who know you have heard the offer. New clients have to come from further out.' },
    steps: [
      {
        label: 'List 10 more people you know', mapLabel: 'List',
        tag: 'TODAY · UNDER 30 MINUTES',
        title: 'Make a list of 10 more people you know who work with brands.',
        desc: 'Former colleagues, past clients and friends in the industry all count. Just names for now.',
        box: () => renderListBox('Where to look', 'Go through these groups:', [
          'Former colleagues who now work at brands',
          "People who've paid you before",
          'Friends who work in marketing or sales'
        ])
      },
      {
        label: 'Send your one-page offer to 5 of them', mapLabel: 'Send', sent: true,
        tag: 'DAY 9–10 · UNDER 30 MINUTES',
        title: 'Send your one-page offer to 5 people on your list.',
        desc: 'Start with the 5 you know best. A personal note beats a polished pitch.',
        box: isId => renderMsgBox('Message to people you know',
          "Hi [Name], hope you're doing well! I'm now helping consumer brands make clear 90-day growth plans. I put together a one-page overview of how it works. Happy to share it if it's useful to you.",
          'Halo [Nama], semoga kabarnya baik! Saat ini saya sedang fokus membantu brand produk sehari-hari menyusun strategi pertumbuhan 90 hari. Saya ada ringkasan 1 halaman tentang pendekatan ini, boleh saya kirimkan barangkali relevan untuk timmu?', isId)
      },
      {
        label: 'Follow up and book calls', mapLabel: 'Call', sent: true,
        tag: 'DAY 11–12 · UNDER 15 MINUTES',
        title: 'Follow up and book a call with anyone who replied.',
        desc: 'Keep it light. One follow-up is enough.',
        box: isId => renderMsgBox('Follow-up WhatsApp message',
          "Hi [Name], following up on the one-page overview I sent. If you have 20 minutes this week, I'd love to hear what's on your plate right now.",
          'Halo [Nama], sekadar follow up soal ringkasan 1 halaman kemarin. Kalau ada waktu 20 menit minggu ini, saya ingin dengar apa yang sedang jadi prioritas kamu.', isId)
      },
      {
        label: 'Turn what you heard into a package', mapLabel: 'Package',
        tag: 'DAY 13 · UNDER 45 MINUTES',
        title: 'Turn what you heard into a simple package.',
        desc: 'Look for what people asked about most. That becomes your first fixed-price offer.',
        box: () => renderListBox('Draft your package', 'Answer these in one line each:', [
          'Who is it for?',
          'What problem does it solve?',
          'What do they get, and in how many weeks?',
          'What does it cost?'
        ])
      },
      CYCLE2_REPORT_STEP
    ]
  }
};

CYCLE2_PLANS.cmo = {
  title: 'Part-time marketing lead',
  pill: '<span class="status-pill open">OPEN</span>',
  success: 'One brand agrees to a 3-month part-time role.',
  diagnosis: { summary: ['Your audits sell, and they pay well. But each one ends, so your income goes up and down.', 'A part-time monthly role could give you income you can count on. This week is about seeing whether that role fits you.'], headline: 'Your audits sell. A monthly role could give you income you can count on.', blockHead: 'Project income is uneven.', blockRest: 'Audits pay well but end. A part-time monthly role gives steadier income.' },
  steps: [
    {
      label: 'List 3 brands that need ongoing help', mapLabel: 'List',
      tag: 'TODAY · UNDER 30 MINUTES',
      title: 'List 3 brands that need marketing help every month, not just once.',
      desc: 'Your audit clients are the best place to start. Who asked "can you keep helping us?"',
      box: () => renderListBox('Where to look', 'Start with these:', [
        'Audit clients who asked for more help afterwards',
        'Brands without a full-time marketing lead',
        'Brands launching something in the next 3 months'
      ])
    },
    {
      label: 'Send a part-time offer to the best fit', mapLabel: 'Send', sent: true,
      tag: 'DAY · UNDER 20 MINUTES',
      title: 'Send a part-time offer to the brand that fits best.',
      desc: 'Keep it simple: how many days a month, what you will own, and the monthly fee.',
      box: isId => renderMsgBox('WhatsApp message, ready to send',
        'Hi [Name], after the audit you asked if I could keep helping. I can: 4 days a month as your part-time marketing lead, for 3 months. I have attached a one-page outline.\n\nCould we talk for 20 minutes this week?',
        'Halo [Nama], setelah audit kemarin kamu sempat tanya apakah saya bisa terus bantu. Bisa: 4 hari per bulan sebagai marketing lead paruh waktu, selama 3 bulan. Ringkasan 1 halamannya saya lampirkan.\n\nBoleh kita ngobrol 20 menit minggu ini?', isId)
    },
    {
      label: 'Call to agree on scope and hours', mapLabel: 'Call',
      tag: 'DAY · 20-MINUTE CALL',
      title: 'Have a 20-minute call to agree on scope and hours.',
      desc: 'Be clear about how many hours you actually have. Two paths are open, and your week is full.',
      box: () => renderListBox('Your call plan', '3 things to agree on:', [
        'What you own, and what stays with their team',
        'How many days a month (and which ones)',
        'When you would start'
      ], true)
    },
    {
      label: 'Send a simple 3-month proposal', mapLabel: 'Proposal',
      tag: 'DAY · UNDER 45 MINUTES',
      title: 'Send a simple 3-month proposal.',
      desc: 'One page is enough. Scope, days per month, monthly fee, start date.',
      box: () => renderListBox('Your proposal', 'Answer in one line each:', [
        'What you will own',
        'Days per month',
        'Monthly fee',
        'Start date'
      ])
    },
    CYCLE2_REPORT_STEP
  ]
};

function getCycle2Plan(pathId) {
  return CYCLE2_PLANS[pathId] || CYCLE2_PLANS.warm;
}

// Variants like 'warm_retest' live on the same lane of the map as 'warm'
function toMapPath(pathId) {
  return String(pathId || 'warm').startsWith('warm') ? 'warm' : pathId;
}
/* ==========================================================================
   90-DAY SCENARIO: a story that misses the goal but passes through every state
   (paths opening, mixed weeks, silence, a missed check-in, the ads temptation,
   two paths competing for time, a plateau). One record per check-in.
   `rp` = monthly income after the check-in, `saved` = money kept in the bank.
   ========================================================================== */
const SCENARIO_MISS = [
  { outcome: 'worked', contacted: 7, replies: 4, calls: 2, paid: 15, rp: 15, saved: 20, paths: ['warm', 'audit'], next: 'audit', event: 'audit-open',
    title: 'Sari signed · Rp15M', note: 'A second contact asked about audit pricing. The audit path opened.' },
  { outcome: 'mixed', contacted: 5, replies: 3, calls: 2, paid: 0, rp: 15, saved: 20, next: 'warm_starter',
    title: 'Interested, but no one paid yet', note: 'Both calls said the first step felt too big. Next: a smaller 2-week version.' },
  { outcome: 'worked', contacted: 2, replies: 2, calls: 1, paid: 7.5, rp: 20, saved: 20, next: 'audit',
    title: 'Second client said yes to the smaller audit', note: 'The smaller first step worked. Back to the full audit offer.' },
  { outcome: 'none', contacted: 6, replies: 0, calls: 0, paid: 0, rp: 20, saved: 20, next: 'warm_retest',
    title: 'No replies this week', note: 'The message was probably too long. Next: a short call instead.' },
  { outcome: 'missed', contacted: 0, replies: 0, calls: 0, paid: 0, rp: 18, saved: 20, next: 'warm_retest', event: 'welcome-back',
    title: 'Check-in missed · life got busy', note: "Sari's project ended, so income dipped. This week shrank to one 15-minute step." },
  { outcome: 'mixed', contacted: 8, replies: 3, calls: 1, paid: 0, rp: 18, saved: 28, next: 'audit', event: 'ads',
    title: 'Tested ads with Rp2M instead of Rp10M', note: 'Chose a capped test over the full Rp10M plan. 1 serious lead, Rp8M kept.' },
  { outcome: 'worked', contacted: 6, replies: 3, calls: 2, paid: 15, rp: 24, saved: 28, paths: ['warm', 'audit', 'cmo'], next: 'audit', event: 'cmo-open',
    title: 'Third client, full price · Rp15M', note: 'Second full-price audit done. The part-time marketing lead path opened.' },
  { outcome: 'worked', contacted: 4, replies: 2, calls: 2, paid: 7.5, rp: 26, saved: 28, next: 'cmo', event: 'capacity',
    title: 'Two paths open, not enough hours', note: 'Audits take 4 h a week, the marketing lead role needs 5. Only 6 h are free.' },
  { outcome: 'mixed', contacted: 5, replies: 2, calls: 1, paid: 0, rp: 24, saved: 28, next: 'cmo',
    title: 'Marketing lead talks stalled', note: 'A monthly client ended. The part-time role is still being discussed.' },
  { outcome: 'none', contacted: 4, replies: 0, calls: 0, paid: 0, rp: 22, saved: 28, next: 'audit',
    title: 'Quiet week', note: 'No new replies. Back to the audit, which is proven.' },
  { outcome: 'mixed', contacted: 6, replies: 3, calls: 2, paid: 0, rp: 22, saved: 28, next: 'audit',
    title: 'Two proposals out, no decision yet', note: 'Both brands said "next month".' },
  { outcome: 'mixed', contacted: 5, replies: 2, calls: 1, paid: 0, rp: 22, saved: 28, next: 'audit',
    title: 'Income holding at Rp22M', note: 'Steady, but not growing. The last week decides what comes next.' },
  { outcome: 'final', contacted: 4, replies: 2, calls: 1, paid: 0, rp: 22, saved: 28, event: 'ending', ending: 'miss',
    title: 'Day 90 · Rp22M a month', note: 'Rp8M a month short of the goal.' }
];
// Same story, but the last 5 check-ins go well: used for the "success ending" preview
const SCENARIO_SUCCESS = SCENARIO_MISS.slice(0, 8).concat([
  { outcome: 'worked', contacted: 5, replies: 3, calls: 2, paid: 6, rp: 27, saved: 28, next: 'cmo',
    title: 'Part-time marketing lead signed · Rp6M a month', note: 'A former audit client took the 3-month part-time role.' },
  { outcome: 'mixed', contacted: 4, replies: 2, calls: 1, paid: 0, rp: 28, saved: 28, next: 'audit',
    title: 'One more audit in the pipeline', note: 'Proposal out, decision next week.' },
  { outcome: 'worked', contacted: 5, replies: 3, calls: 2, paid: 15, rp: 29, saved: 28, next: 'audit',
    title: 'Fourth full-price audit · Rp15M', note: 'The audit and the part-time role now run side by side.' },
  { outcome: 'worked', contacted: 3, replies: 2, calls: 2, paid: 7.5, rp: 30, saved: 28, next: 'audit',
    title: 'Goal reached · Rp30M a month', note: 'Monthly income hit the goal on Day 84.' },
  { outcome: 'final', contacted: 3, replies: 2, calls: 1, paid: 0, rp: 31, saved: 28, event: 'ending', ending: 'success',
    title: 'Day 90 · Rp31M a month', note: 'Goal reached, with Rp28M still in the bank.' }
]);

/* ==========================================================================
   V11 DEMO FIXTURES (record D3): the prototype's engine snapshots, one per sample workspace. Demo mode reads them through
   V11_ENGINE (live-vm.js), the same seam the live adapter feeds. engineApplyUpdate recomposes a snapshot the way an
   engine update would; it is demo-only and is never called in live mode.
   ========================================================================== */
/* ── ported from Revenue Navigation v11.dc.html lines 3720-4103 ── */
function engineReq(id, label, satisfaction) { return { id, label, satisfaction }; }
function enginePath(p) {
  return Object.assign({
    id: '', title: '', group: 'Other possibilities', status_display: 'NOT YET',
    lifecycle: 'OPEN', stop_source: null, requirements: [], evidence_ids: [],
    provenance: 'From your Talk', trail: [], next_move: null
  }, p);
}
function engineEvidence(ev) {
  return Object.assign({ id: '', source: '', quote: '', day: null, disputed: false }, ev);
}

/* Seed snapshots: deterministic per map, aligned with each workspace's story. */
function engineSeedSnapshot(key) {
  const seeded = {
    dimas: engineSnapshotDimas,
    rina: engineSnapshotRina,
    arif: engineSnapshotArif,
    bayu: engineSnapshotBayu
  }[key];
  if (seeded) return seeded();
  /* A brand-new map starts empty: nothing is known yet, no possibilities apply.
     This is the honest zero — the entry flow (Talk) fills it, never the UI. */
  return {
    goal: { text: 'Not set yet', now: 'Not set yet', horizon: null },
    paths: [],
    overflow: 0,
    state: null,
    evidence: [],
    nextmove: null
  };
}

function engineSnapshotDimas() {
  return {
    goal: { text: 'Rp30M a month', now: 'Rp0', horizon: 'Day 90' },
    overflow: 0,
    paths: [
      enginePath({
        id: 'advise-network', title: 'Advising people you know', group: 'Warm introductions',
        status_display: 'OPEN',
        requirements: [
          engineReq('demand', 'People already asked for this', 'PRESENT'),
          engineReq('offer', 'A written offer they can say yes to', 'ABSENT'),
          engineReq('hours', 'Fits the hours you have', 'PRESENT')
        ],
        evidence_ids: ['ev-asks', 'ev-savings'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Appeared on your map from your Talk'],
        next_move: { type: 'ACTION', title: 'Send a one-page offer to the 2 contacts who asked', why: 'It gives the people who asked something to say yes to.' }
      }),
      enginePath({
        id: 'office-ads-company', title: 'Office, ads, a company', group: 'Scale-up moves',
        status_display: 'STOP', lifecycle: 'STOPPED', stop_source: 'evidence',
        requirements: [
          engineReq('demand', 'Demand beyond your network', 'UNKNOWN'),
          engineReq('runway', 'Runway that survives a slow month', 'ABSENT')
        ],
        evidence_ids: ['ev-savings'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Stopped by what your Talk showed: Rp20M of savings stays safe']
      }),
      enginePath({
        id: 'agency-retainer', title: 'Retainer work for agencies', group: 'Warm introductions',
        status_display: 'NOT YET',
        requirements: [
          engineReq('demand', 'An agency that answers', 'UNKNOWN'),
          engineReq('hours', 'Fits the hours you have', 'UNKNOWN'),
          engineReq('offer', 'A written offer they can say yes to', 'ABSENT')
        ],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Noted as possible, nothing confirmed yet']
      }),
      enginePath({
        id: 'productized-audit', title: 'A fixed-price brand audit', group: 'Packaged offers',
        status_display: 'TEST FIRST',
        requirements: [
          engineReq('demand', 'A past client who wants one', 'PARTIAL'),
          engineReq('offer', 'A written offer they can say yes to', 'ABSENT'),
          engineReq('price', 'A price that covers your hours', 'UNKNOWN')
        ],
        evidence_ids: ['ev-asks'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Possible, test before committing']
      }),
      enginePath({
        id: 'workshop-teaching', title: 'Paid workshop for founders', group: 'Packaged offers',
        status_display: 'NOT YET',
        requirements: [
          engineReq('demand', 'People who would pay for it', 'UNKNOWN'),
          engineReq('offer', 'A written offer they can say yes to', 'ABSENT')
        ],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Noted as possible, nothing confirmed yet']
      })
    ],
    state: {
      where_you_are: 'You left your marketing job to build a consulting practice. Two people have already asked to pay you. Nothing is written down for them to say yes to, so the asks go quiet.',
      blocking: 'There is no offer. Your skills and the demand are real; what is missing is the thing in between.',
      why_we_think_so: ['Two past colleagues asked what you charge', 'Rp20M of savings, about 5 weeks', 'You have ~6 free hours a week'],
      what_not_to_do: ['Don’t lease an office', 'Don’t run paid ads yet', 'Don’t register a company yet'],
      next_best_action: 'Send a one-page offer to the 2 contacts who asked.',
      know_right_when: 'At least 1 of the 2 replies wants to talk about a real project.',
      when_to_reassess: 'After this week’s check-in, or the moment a third person asks.',
      uncertain: ['Whether agencies would answer at your hours', 'What a fixed-price audit should cost'],
      changed: ['Day 1 · State created from your Talk']
    },
    evidence: [
      engineEvidence({ id: 'ev-asks', source: 'Your Talk · Day 1', quote: 'Two people asked to pay me once I start.', day: 1 }),
      engineEvidence({ id: 'ev-savings', source: 'Your Talk · Day 1', quote: 'Rp20M saved, about 5 weeks of runway.', day: 1 })
    ],
    nextmove: { type: 'ACTION', title: 'Send your one-page offer to the 2 contacts who asked.', minutes: 30, path_id: 'advise-network' }
  };
}

function engineSnapshotRina() {
  return {
    goal: { text: 'Rp35M a month', now: 'Rp12M', horizon: 'Day 90' },
    overflow: 0,
    paths: [
      enginePath({
        id: 'small-test', title: 'A small test, either way', group: 'Buyer conversations',
        status_display: 'OPEN',
        requirements: [
          engineReq('buyers', 'Past buyers you can reach', 'PRESENT'),
          engineReq('ask', 'A question set that settles which explanation is right', 'PRESENT')
        ],
        evidence_ids: ['ev-rina-buyers'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Appeared on your map from your Talk'],
        next_move: { type: 'ACTION', title: 'Ask 3 past buyers what they were looking for', why: 'Their answers settle which explanation is right.' }
      }),
      enginePath({
        id: 'office-ads-company', title: 'Office, ads, a company', group: 'Scale-up moves',
        status_display: 'STOP', lifecycle: 'STOPPED', stop_source: 'evidence',
        requirements: [engineReq('diagnosis', 'A settled explanation of what holds sales back', 'UNKNOWN')],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Stopped for now: no settled explanation yet']
      }),
      enginePath({
        id: 'reach-new-buyers', title: 'Reach more new buyers', group: 'Buyer conversations',
        status_display: 'NOT YET',
        requirements: [engineReq('evidence', 'Signs that not enough new buyers find you', 'UNKNOWN')],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Waits for the small test’s answer']
      }),
      enginePath({
        id: 'raise-prices', title: 'Raise your prices', group: 'Pricing',
        status_display: 'NOT YET',
        requirements: [engineReq('evidence', 'Signs that prices don’t cover your hours', 'UNKNOWN')],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Waits for the small test’s answer']
      }),
      enginePath({
        id: 'bring-buyers-back', title: 'Bring past buyers back', group: 'Buyer conversations',
        status_display: 'NOT YET',
        requirements: [engineReq('evidence', 'Signs that past buyers don’t come back', 'UNKNOWN')],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Waits for the small test’s answer']
      })
    ],
    state: {
      where_you_are: 'Your craft studio earns Rp12M of the Rp35M you want. Three explanations are still close: not enough new buyers, prices that don’t cover your hours, or past buyers who don’t return.',
      blocking: 'The explanation isn’t settled yet, so the map starts with a test that helps under all three.',
      why_we_think_so: ['Rp12M a month from returning buyers', 'No steady stream of new buyers', 'Prices haven’t moved in a year'],
      what_not_to_do: ['Don’t lease an office', 'Don’t run ads yet', 'Don’t register a company yet'],
      next_best_action: 'Ask 3 past buyers what they were looking for when they found you.',
      know_right_when: 'The 3 answers point clearly at one of the three explanations.',
      when_to_reassess: 'At your next check-in, or sooner if a buyer answers with something unexpected.',
      uncertain: ['Which of the three explanations is right'],
      changed: ['Day 1 · State created from your Talk']
    },
    evidence: [
      engineEvidence({ id: 'ev-rina-buyers', source: 'Your Talk · Day 1', quote: 'Most months a few past buyers come back on their own.', day: 1 })
    ],
    nextmove: { type: 'EVIDENCE_REQUEST', title: 'Ask 3 past buyers what they were looking for.', minutes: 25, path_id: 'small-test' }
  };
}

function engineSnapshotArif() {
  return {
    goal: { text: 'Rp30M a month', now: 'Rp18M', horizon: 'Day 90' },
    overflow: 0,
    paths: [
      enginePath({
        id: 'fixed-audit', title: 'A fixed-price brand audit', group: 'Packaged offers',
        status_display: 'OPEN',
        requirements: [
          engineReq('demand', 'Returning clients asked for it', 'PRESENT'),
          engineReq('hours', 'Fits your 6 free hours a week', 'PRESENT'),
          engineReq('price', 'A price that covers your hours', 'PRESENT')
        ],
        evidence_ids: ['ev-arif-audit'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Appeared on your map', 'Check-in 2 · 2 returning clients asked for an audit'],
        next_move: { type: 'ACTION', title: 'Package the audit the two returning clients asked for', why: 'Demand is proven; it only needs a shape.' }
      }),
      enginePath({
        id: 'agency-freelance', title: 'Freelancing for agencies', group: 'Warm introductions',
        status_display: 'NOT YET',
        requirements: [
          engineReq('hours', 'Fits your 6 free hours a week', 'ABSENT'),
          engineReq('demand', 'An agency that answers', 'UNKNOWN')
        ],
        evidence_ids: [],
        provenance: 'From your Talk · Day 1',
        trail: ['Check-in 2 · Held back: it would go past your hours']
      }),
      enginePath({
        id: 'hire-help', title: 'Hire junior help', group: 'Scale-up moves',
        status_display: 'TEST FIRST',
        requirements: [
          engineReq('demand', 'More work than your hours', 'PRESENT'),
          engineReq('money', 'Enough incoming to cover a salary', 'PARTIAL')
        ],
        evidence_ids: ['ev-arif-audit'],
        provenance: 'From check-ins · Week 2',
        trail: ['Check-in 2 · Test with one small delegated job first']
      })
    ],
    state: {
      where_you_are: 'People already pay you and come back. You have Rp18M of Rp30M so far. The limit is time: about 6 free hours a week.',
      blocking: 'The next client has to fit inside the hours you have, or the hours have to grow first.',
      why_we_think_so: ['2 returning clients asked for an audit', 'Rp18M earned by Day 15', '~6 free hours a week'],
      what_not_to_do: ['Don’t take hourly freelance work for agencies', 'Don’t hire before one delegated job works'],
      next_best_action: 'Package the fixed-price audit two returning clients asked for.',
      know_right_when: 'One audit is sold at a price that covers your hours.',
      when_to_reassess: 'When the audit is packaged, or if a third client asks.',
      uncertain: ['What junior help should cost vs. free hours'],
      changed: ['Check-in 2 · Two clients asked for an audit, so the audit path opened']
    },
    evidence: [
      engineEvidence({ id: 'ev-arif-audit', source: 'Client note · Check-in 2', quote: '2 returning clients asked for a brand audit.', day: 14 })
    ],
    nextmove: { type: 'ACTION', title: 'Package the audit two returning clients asked for.', minutes: 45, path_id: 'fixed-audit' }
  };
}

function engineSnapshotBayu() {
  return {
    goal: { text: 'Rp25M a month', now: 'Rp0', horizon: 'Day 90' },
    overflow: 0,
    paths: [
      enginePath({
        id: 'quick-cash', title: 'Quick cash from your network', group: 'Warm introductions',
        status_display: 'OPEN',
        requirements: [
          engineReq('speed', 'Can pay within 60 days', 'PRESENT'),
          engineReq('fit', 'Matches what you already do', 'PRESENT')
        ],
        evidence_ids: ['ev-bayu-savings'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Opened as the safety-first path'],
        next_move: { type: 'ACTION', title: 'Offer a one-off paid project or a short contract', why: 'Savings cover ~5 weeks; paid work needs to start flowing.' }
      }),
      enginePath({
        id: 'consulting-goal', title: 'The consulting practice you wanted', group: 'Packaged offers',
        status_display: 'NOT YET', lifecycle: 'PAUSED', stop_source: 'you',
        requirements: [
          engineReq('runway', 'Runway that survives a slow month', 'ABSENT'),
          engineReq('demand', 'Clients beyond your network', 'UNKNOWN')
        ],
        evidence_ids: ['ev-bayu-savings'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Paused by you until quick cash is flowing']
      }),
      enginePath({
        id: 'office-ads', title: 'Office and paid ads', group: 'Scale-up moves',
        status_display: 'STOP', lifecycle: 'STOPPED', stop_source: 'evidence',
        requirements: [engineReq('runway', 'Runway that survives a slow month', 'ABSENT')],
        evidence_ids: ['ev-bayu-savings'],
        provenance: 'From your Talk · Day 1',
        trail: ['Day 1 · Stopped by what your Talk showed: 5 weeks of runway']
      })
    ],
    state: {
      where_you_are: 'Your design studio hasn’t earned yet and savings cover about 5 weeks. The goal stands; the order changes.',
      blocking: 'Runway, not demand: paid work needs to arrive within 60 days before anything else.',
      why_we_think_so: ['Rp6M saved, about 5 weeks', 'No paying client yet', 'A network that answers fast'],
      what_not_to_do: ['Don’t lease an office', 'Don’t run paid ads'],
      next_best_action: 'Offer a one-off paid project or a short contract to people who know your work.',
      know_right_when: 'One paid project starts within 60 days.',
      when_to_reassess: 'At the first check-in after the first paid project.',
      uncertain: ['How quickly your network converts to paid work'],
      changed: ['Day 1 · State created from your Talk']
    },
    evidence: [
      engineEvidence({ id: 'ev-bayu-savings', source: 'Your Talk · Day 1', quote: 'Rp6M saved, about 5 weeks.', day: 1 })
    ],
    nextmove: { type: 'ACTION', title: 'Offer a one-off paid project or a short contract.', minutes: 30, path_id: 'quick-cash' }
  };
}

/* Engine-shaped updates: the only way a snapshot changes. Each mirrors what the
   real engine does — evidence never un-happens, UNKNOWN can become PRESENT or
   stay UNKNOWN, and user decisions land as trail events, never silent flips. */
function engineApplyUpdate(snap, update) {
  const next = JSON.parse(JSON.stringify(snap));
  const path = id => next.paths.find(p => p.id === id);
  switch (update.type) {
    case 'evidence-added': {
      const ev = engineEvidence(update.evidence);
      next.evidence.push(ev);
      (update.requirement_hits || []).forEach(hit => {
        const p = path(hit.path_id);
        const r = p && p.requirements.find(r => r.id === hit.requirement_id);
        if (r) {
          if (r.satisfaction === 'UNKNOWN' || r.satisfaction === 'PARTIAL') r.satisfaction = hit.satisfaction || 'PRESENT';
          p.evidence_ids.push(ev.id);
          p.trail.push(`Day ${ev.day || 'unknown'} · ${ev.quote} · ${r.label.toLowerCase()}: ${r.satisfaction === 'PRESENT' ? 'now true' : 'still partial'}`);
        }
      });
      next.paths.forEach(p => {
        if (p.lifecycle !== 'OPEN') return;
        const sat = p.requirements.map(r => r.satisfaction);
        const absent = sat.includes('ABSENT');
        const unknown = sat.includes('UNKNOWN');
        const present = sat.filter(s => s === 'PRESENT').length;
        if (p.status_display !== 'STOP') {
          if (!absent && present >= Math.max(1, Math.ceil(sat.length / 2)) && !unknown) p.status_display = 'OPEN';
          else if (!absent && present > 0 && unknown) p.status_display = 'TEST FIRST';
          else if (p.status_display === 'NOT YET' && present > 0 && !absent) p.status_display = 'TEST FIRST';
        }
      });
      break;
    }
    case 'dispute-raised': {
      const ev = next.evidence.find(e => e.id === update.evidence_id);
      if (ev) ev.disputed = true;   // shown, never silently resolved; status unchanged
      break;
    }
    case 'path-stopped-by-you': {
      const p = path(update.path_id);
      if (p) {
        p.stop_source = 'you';
        p.lifecycle = update.pause ? 'PAUSED' : 'STOPPED';
        p.status_display = 'STOP';
        p.trail.push(update.pause ? 'Paused by you' : 'Stopped by you. Your decision, recorded here');
      }
      break;
    }
    case 'path-resumed-by-you': {
      const p = path(update.path_id);
      if (p && p.stop_source === 'you') {
        p.stop_source = null; p.lifecycle = 'OPEN';
        p.status_display = p.requirements.some(r => r.satisfaction === 'ABSENT') ? 'NOT YET' : 'TEST FIRST';
        p.trail.push('Re-opened by you. You chose to go ahead anyway, recorded as your decision');
      }
      break;
    }
    case 'outcome-reported': {
      const p = path(update.path_id);
      if (p) {
        p.trail.push(`Day ${update.day || 'unknown'} · You reported: ${update.outcome}`);
        next.evidence.push(engineEvidence({
          id: update.evidence_id || `ev-${p.id}-${update.day || 'x'}`,
          source: `Your check-in · Day ${update.day || 'unknown'}`,
          quote: update.note || update.outcome, day: update.day || null
        }));
      }
      break;
    }
    case 'goal-changed': {
      next.goal = Object.assign({}, next.goal, update.goal || {});
      next.paths.forEach(p => p.trail.push(`Goal changed. Paths re-checked against “${update.goal && update.goal.text}”`));
      break;
    }
    case 'state-refreshed': {
      if (update.state) next.state = Object.assign({}, next.state, update.state);
      break;
    }
    default: break;
  }
  /* Presentation cap: at most PATH_VIEW_CAP nodes shown, the rest are the
     overflow count. Order comes from the snapshot (this array), not the UI. */
  next.overflow = Math.max(0, next.paths.length - PATH_VIEW_CAP);
  return next;
}
