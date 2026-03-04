import { chromium } from 'playwright';

const INTERVIEW_URL = 'https://app.qvantify.com/?interview=20ab1e5b-54c4-4f03-8331-4f88132d3b51&external_id=AI_test';

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  });
  const page = await context.newPage();

  try {
    console.log('Navigating to:', INTERVIEW_URL);
    await page.goto(INTERVIEW_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    
    // Wait for interview to load
    let loaded = false;
    for (let attempt = 0; attempt < 30; attempt++) {
      const text = await page.innerText('body').catch(() => '');
      if (text && text.length > 50 && !text.includes('Loading interview')) {
        loaded = true;
        console.log(`Interview loaded after ${attempt + 1}s`);
        break;
      }
      await page.waitForTimeout(1000);
    }

    if (!loaded) {
      console.error('Interview never finished loading');
      return;
    }

    // Interview loop
    for (let round = 0; round < 40; round++) {
      await page.waitForTimeout(2000);
      const pageContent = await page.innerText('body').catch(() => '');
      const lowerContent = pageContent.toLowerCase();

      console.log(`--- Round ${round + 1} ---`);
      console.log('Page text snippet:', pageContent.trim().slice(0, 300));

      if (
        lowerContent.includes('thank you') ||
        lowerContent.includes('completed') ||
        lowerContent.includes('interview is complete') ||
        lowerContent.includes('all done')
      ) {
        console.log('Interview completed!');
        break;
      }

      const inputSelector = 'input[type="text"], textarea, [contenteditable="true"]';
      const hasInput = await page.locator(inputSelector).first().isVisible().catch(() => false);

      if (hasInput) {
        // Persona: Online casino player, plays for free, short responses.
        let answer = 'Yes, for free.';
        
        if (lowerContent.includes('how much') || lowerContent.includes('money') || lowerContent.includes('spend')) {
          answer = 'Nothing, just free.';
        } else if (lowerContent.includes('how often') || lowerContent.includes('frequently')) {
          answer = 'Once a week.';
        } else if (lowerContent.includes('why') || lowerContent.includes('reason')) {
          answer = 'For fun.';
        } else if (lowerContent.includes('experience') || lowerContent.includes('feel')) {
          answer = 'It was fun.';
        } else if (lowerContent.includes('recommend')) {
          answer = 'Yes.';
        } else if (lowerContent.includes('game') || lowerContent.includes('play')) {
          answer = 'Slots for free.';
        }

        console.log(`Answering: "${answer}"`);
        await page.locator(inputSelector).first().fill(answer);
        await page.waitForTimeout(500);
      }

      const buttonSelectors = [
        'button:has-text("Reply")',
        'button:has-text("Send")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
        'button:has-text("Submit")',
      ];

      let clicked = false;
      for (const sel of buttonSelectors) {
        const btn = page.locator(sel).first();
        if (await btn.isVisible().catch(() => false) && await btn.isEnabled().catch(() => false)) {
          console.log(`Clicking: ${sel}`);
          await btn.click();
          clicked = true;
          break;
        }
      }

      if (!clicked && hasInput) {
        console.log('No button, pressing Enter');
        await page.keyboard.press('Enter');
      } else if (!clicked) {
        console.log('No action taken, waiting for AI...');
      }

      await page.waitForTimeout(4000);
    }

  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await browser.close();
  }
}

run();
