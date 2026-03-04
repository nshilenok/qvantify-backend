import { chromium } from 'playwright';

const INTERVIEW_URL = 'https://app.qvantify.com/?interview=0de9c996-b059-4395-9d7e-31f6ce51baf5&external_id=free_player_test';

async function run() {
  console.log('Starting Playwright script for free player persona...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
  });
  const page = await context.newPage();

  try {
    console.log('Navigating to:', INTERVIEW_URL);
    await page.goto(INTERVIEW_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
    
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
      await page.waitForTimeout(3000);
      const pageContent = await page.innerText('body').catch(() => '');
      const lowerContent = pageContent.toLowerCase();

      console.log(`\n--- Round ${round + 1} ---`);
      
      const lines = pageContent.split('\n').filter(l => l.trim().length > 0);
      const recentContext = lines.slice(Math.max(0, lines.length - 10)).join('\n');
      console.log('Recent page context:\n' + recentContext);

      // Be careful not to match polite words in questions
      if (
        lowerContent.includes('interview is complete') ||
        lowerContent.includes('all done') ||
        lowerContent.includes('wrap up') ||
        lowerContent.includes('thank you for completing')
      ) {
        console.log('Interview appears to be completed!');
        break;
      }

      const inputSelector = 'input[type="text"], textarea, [contenteditable="true"]';
      const hasInput = await page.locator(inputSelector).first().isVisible().catch(() => false);
      const isInputEnabled = await page.locator(inputSelector).first().isEnabled().catch(() => false);

      if (hasInput && isInputEnabled) {
        // Persona logic: Free player
        let answer = 'I never buy coins. I just use free spins and daily rewards to play.';
        
        if (lowerContent.includes('how much') || lowerContent.includes('money') || lowerContent.includes('spend') || lowerContent.includes('deposit')) {
          answer = 'I never deposit or spend real money. I only use free sweeps coins, demo modes, or no-deposit bonuses.';
        } else if (lowerContent.includes('how often') || lowerContent.includes('frequently')) {
          answer = 'I play almost every day since it\'s free and I don\'t have to worry about losing money.';
        } else if (lowerContent.includes('why') || lowerContent.includes('reason') || lowerContent.includes('motivation')) {
          answer = 'I enjoy the thrill of the games without the financial risk. It\'s just pure entertainment for me.';
        } else if (lowerContent.includes('experience') || lowerContent.includes('feel')) {
          answer = 'It is a lot of fun, especially when I hit a big win with free spins.';
        } else if (lowerContent.includes('recommend')) {
          answer = 'Yes, I highly recommend playing for free. It\'s a great way to pass the time safely.';
        } else if (lowerContent.includes('game') || lowerContent.includes('play')) {
          answer = 'Mainly slot games and sometimes social casino table games. Whatever gives me the best free bonuses.';
        } else if (lowerContent.includes('casino') || lowerContent.includes('site') || lowerContent.includes('platform')) {
          answer = 'I stick to social casinos or sites that give generous daily login bonuses so I never have to pay.';
        } else if (lowerContent.includes('considered') || lowerContent.includes('prefer')) {
          answer = 'I have considered it, but honestly I prefer to stick with the free options because I play just for fun.';
        } else if (lowerContent.includes('free options') || lowerContent.includes('stick with free')) {
          answer = 'The free options give me everything I need without any stress.';
        } else if (lowerContent.includes('purchase')) {
           answer = 'I don\'t plan on making any purchases, it\'s not necessary for me to have fun.';
        }

        console.log(`[AI Player] Answering: "${answer}"`);
        await page.locator(inputSelector).first().fill(answer);
        await page.waitForTimeout(1000);
        
        console.log('Clicking the Send button');
        const sendButton = page.locator('button:has-text("Send")').first();
        if (await sendButton.isVisible().catch(() => false)) {
          await sendButton.click();
        } else {
          await page.keyboard.press('Enter');
        }
      } else {
        const buttonSelectors = [
          'button:has-text("Reply")',
          'button:has-text("Next")',
          'button:has-text("Continue")',
          'button:has-text("Submit")',
          'button:has-text("Start")',
          'button:has-text("Begin")',
        ];

        let clicked = false;
        for (const sel of buttonSelectors) {
          const btn = page.locator(sel).first();
          if (await btn.isVisible().catch(() => false) && await btn.isEnabled().catch(() => false)) {
            console.log(`Clicking button: ${sel}`);
            await btn.click();
            clicked = true;
            break;
          }
        }
        
        if (!clicked) {
           console.log('Waiting for AI or next prompt...');
        }
      }

      await page.waitForTimeout(6000); // Wait for the AI interviewer to generate the next question
    }

  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await browser.close();
    console.log('Script finished.');
  }
}

run();
