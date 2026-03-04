import { chromium } from 'playwright';

const INTERVIEW_URL = 'https://app.qvantify.com/interview?interview=20ab1e5b-54c4-4f03-8331-4f88132d3b51&external_id=robot_test';

const PERSONAS = [
  {
    id: 1,
    name: 'Casual buyer – yes purchase',
    didPurchase: true,
    purchaseDetails: 'Yes, I deposited $50 last week and played some slots.',
    spendAmount: '$50',
    frequency: 'Once or twice a month',
    motivation: 'I wanted some entertainment after a stressful week.',
    experience: 'It was okay, I lost a bit but had fun.',
    paymentIssues: 'No issues, the payment went through instantly.',
    recommend: 'Probably yes, the site was easy to use.',
  },
  {
    id: 2,
    name: 'Non-buyer – no purchase',
    didPurchase: false,
    purchaseDetails: 'No, I browsed but decided not to deposit.',
    spendAmount: 'Nothing',
    frequency: 'I rarely visit casino sites.',
    motivation: 'I was curious but did not feel comfortable spending money.',
    experience: 'I just looked around for a few minutes.',
    paymentIssues: 'N/A, I did not make a payment.',
    recommend: 'Not sure, I did not actually use the service.',
  },
  {
    id: 3,
    name: 'Regular buyer – yes purchase (slots focus)',
    didPurchase: true,
    purchaseDetails: 'Yes, I deposited $100 last week and played slots for a couple of hours.',
    spendAmount: '$100',
    frequency: 'About once a week',
    motivation: 'I enjoy slots, it is a fun way to relax.',
    experience: 'Mixed – I won a small amount but then lost it back.',
    paymentIssues: 'No, everything was smooth.',
    recommend: 'Yes, the variety of games was good.',
  },
  {
    id: 4,
    name: 'Browser only – no purchase',
    didPurchase: false,
    purchaseDetails: 'No, I looked at the casino site but left without making any deposit.',
    spendAmount: 'Zero',
    frequency: 'I visit casino sites rarely, maybe once every few months.',
    motivation: 'I was checking out what was available but did not want to spend.',
    experience: 'I only saw the lobby screen before leaving.',
    paymentIssues: 'N/A',
    recommend: 'I cannot say, I did not try the service.',
  },
  {
    id: 5,
    name: 'High spender – yes purchase',
    didPurchase: true,
    purchaseDetails: 'Yes, I have been playing regularly and deposited around $500 last month.',
    spendAmount: '$500',
    frequency: 'Several times a week',
    motivation: 'I enjoy the thrill and I like table games like blackjack and roulette.',
    experience: 'Mostly positive, I have had some good wins.',
    paymentIssues: 'No problems at all, withdrawals are usually fast.',
    recommend: 'Yes, I have recommended it to a few friends.',
  },
];

async function runSession(persona) {
  const log = [];
  const issues = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  });
  const page = await context.newPage();

  const addLog = (msg) => {
    console.log(`[Session ${persona.id}] ${msg}`);
    log.push(msg);
  };

  const addIssue = (msg) => {
    console.warn(`[Session ${persona.id}] ISSUE: ${msg}`);
    issues.push(msg);
  };

  try {
    addLog(`Navigating to interview URL...`);
    await page.goto(INTERVIEW_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Check for loading state
    const bodyText = await page.innerText('body').catch(() => '');
    addLog(`Initial page content snippet: ${bodyText.slice(0, 200)}`);

    // Wait for interview to actually load (up to 15s)
    let loaded = false;
    for (let attempt = 0; attempt < 15; attempt++) {
      const text = await page.innerText('body').catch(() => '');
      if (text && text.length > 50 && !text.includes('Loading interview')) {
        loaded = true;
        addLog(`Interview loaded after ${attempt + 1}s`);
        break;
      }
      await page.waitForTimeout(1000);
    }

    if (!loaded) {
      addIssue('Interview never finished loading after 15 seconds');
      const screenshot = await page.screenshot({ path: `/tmp/session_${persona.id}_stuck.png`, fullPage: true });
      addLog('Saved stuck screenshot');
    }

    // Main interview loop – up to 40 rounds of interactions
    let completedNormally = false;
    for (let round = 0; round < 40; round++) {
      await page.waitForTimeout(1500);

      const pageContent = await page.innerText('body').catch(() => '');
      addLog(`--- Round ${round + 1} page text: ${pageContent.slice(0, 300)}`);

      // Check for completion
      const lowerContent = pageContent.toLowerCase();
      if (
        lowerContent.includes('thank you') ||
        lowerContent.includes('completed') ||
        lowerContent.includes('interview is complete') ||
        lowerContent.includes('all done') ||
        lowerContent.includes('that\'s all') ||
        lowerContent.includes('thats all')
      ) {
        addLog('Detected completion screen!');
        completedNormally = true;
        break;
      }

      // Check for error states
      if (
        lowerContent.includes('error') ||
        lowerContent.includes('something went wrong') ||
        lowerContent.includes('oops')
      ) {
        addIssue(`Error state detected: ${pageContent.slice(0, 200)}`);
        await page.screenshot({ path: `/tmp/session_${persona.id}_error_round${round}.png`, fullPage: true });
      }

      // Find text input or textarea
      const inputSelector = 'input[type="text"], textarea, [contenteditable="true"]';
      const hasInput = await page.locator(inputSelector).first().isVisible().catch(() => false);

      if (hasInput) {
        // Read the current question/prompt to choose a good answer
        const questionText = pageContent.toLowerCase();
        let answer = 'I am not sure.';

        if (questionText.includes('purchase') || questionText.includes('deposit') || questionText.includes('buy') || questionText.includes('paid') || questionText.includes('spend') || questionText.includes('spent')) {
          answer = persona.didPurchase ? persona.purchaseDetails : persona.purchaseDetails;
        } else if (questionText.includes('how much') || questionText.includes('amount') || questionText.includes('money')) {
          answer = persona.spendAmount;
        } else if (questionText.includes('how often') || questionText.includes('frequent') || questionText.includes('regularity')) {
          answer = persona.frequency;
        } else if (questionText.includes('why') || questionText.includes('reason') || questionText.includes('motivat')) {
          answer = persona.motivation;
        } else if (questionText.includes('experience') || questionText.includes('feel') || questionText.includes('opinion') || questionText.includes('think')) {
          answer = persona.experience;
        } else if (questionText.includes('payment') || questionText.includes('issue') || questionText.includes('problem')) {
          answer = persona.paymentIssues;
        } else if (questionText.includes('recommend') || questionText.includes('suggest') || questionText.includes('others')) {
          answer = persona.recommend;
        } else {
          // Generic responses
          answer = persona.didPurchase
            ? 'Yes, I had a generally positive experience.'
            : 'I did not make a purchase but I was interested in the service.';
        }

        addLog(`Typing answer: "${answer}"`);
        await page.locator(inputSelector).first().click();
        await page.locator(inputSelector).first().fill(answer);
        await page.waitForTimeout(500);
      }

      // Look for submit/next/reply button
      const buttonSelectors = [
        'button[type="submit"]',
        'button:has-text("Reply")',
        'button:has-text("Send")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button:has-text("Submit")',
        '[role="button"]:has-text("Reply")',
        '[role="button"]:has-text("Send")',
      ];

      let clicked = false;
      for (const sel of buttonSelectors) {
        const btn = page.locator(sel).first();
        const visible = await btn.isVisible().catch(() => false);
        const enabled = await btn.isEnabled().catch(() => false);
        if (visible && enabled) {
          addLog(`Clicking button: ${sel}`);
          await btn.click();
          clicked = true;
          break;
        }
      }

      if (!clicked) {
        // Try pressing Enter if there is an input
        if (hasInput) {
          addLog('No button found, pressing Enter');
          await page.keyboard.press('Enter');
        } else {
          addLog('No input and no button found – waiting...');
          // Check if we're on a waiting/thinking state
          if (lowerContent.includes('thinking') || lowerContent.includes('...') || lowerContent.includes('typing')) {
            await page.waitForTimeout(3000);
            continue;
          }
          addIssue(`Stuck at round ${round + 1} – no input and no button visible`);
          await page.screenshot({ path: `/tmp/session_${persona.id}_stuck_round${round}.png`, fullPage: true });
          break;
        }
      }

      // Wait after action for AI response
      await page.waitForTimeout(4000);
    }

    const finalText = await page.innerText('body').catch(() => '');
    addLog(`Final page text: ${finalText.slice(0, 500)}`);

    if (!completedNormally) {
      addIssue('Interview did not reach a clear completion screen within 40 rounds');
      await page.screenshot({ path: `/tmp/session_${persona.id}_final.png`, fullPage: true });
    }

    return {
      sessionId: persona.id,
      persona: persona.name,
      didPurchase: persona.didPurchase,
      completedNormally,
      log,
      issues,
    };

  } catch (err) {
    addIssue(`Fatal error: ${err.message}`);
    await page.screenshot({ path: `/tmp/session_${persona.id}_crash.png`, fullPage: true }).catch(() => {});
    return {
      sessionId: persona.id,
      persona: persona.name,
      didPurchase: persona.didPurchase,
      completedNormally: false,
      log,
      issues,
    };
  } finally {
    await browser.close();
  }
}

// Run all 5 sessions in parallel
const results = await Promise.all(PERSONAS.map(runSession));

console.log('\n\n========== FINAL REPORT ==========\n');
for (const r of results) {
  console.log(`\n--- Session ${r.sessionId}: ${r.persona} (purchased: ${r.didPurchase}) ---`);
  console.log(`Completed normally: ${r.completedNormally}`);
  if (r.issues.length > 0) {
    console.log(`ISSUES (${r.issues.length}):`);
    r.issues.forEach(i => console.log(`  ⚠ ${i}`));
  } else {
    console.log('No issues detected.');
  }
  console.log('\nFull log:');
  r.log.forEach(l => console.log(`  ${l}`));
}
