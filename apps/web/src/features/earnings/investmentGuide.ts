/** A curated reading list for investing and betting - Kenya and America.

 * These are the same static notes on every machine: nothing here is a record,
 * a rate or a projection, and none of it is saved to your database. LifeSmart
 * is not connected to any of these sites - it does not know what a share costs
 * today, whether a platform still accepts Kenyan residents, or whether a
 * provider is telling the truth. So every entry is only *where to look* and
 * *what to watch out for*; the deciding and the money always stay with you.
 *
 * The order follows the recommended path: learn first, practise with virtual
 * money, research companies, and only then consider a regulated provider. */

export type GuideCategory =
  | "Learn"
  | "Practise"
  | "Research"
  | "Check a provider"
  | "Kenyan shares"
  | "US & global shares"
  | "Betting";

export interface GuideEntry {
  name: string;
  url: string;
  category: GuideCategory;
  /** Where the platform operates, shown as a small tag. */
  tags: string[];
  summary: string;
  /** How to open an account, or how to use the site if no account is needed. */
  steps: string[];
  /** What you can actually do there once you are in. */
  use: string[];
  /** How the money can be lost, or why the figures are not a promise. */
  caution: string;
  /** For the resources that are neither a market nor a betting site. */
  benefit?: string;
}

export const GUIDE_ENTRIES: GuideEntry[] = [
  {
    name: "Investor.gov",
    url: "https://www.investor.gov/",
    category: "Learn",
    tags: ["America", "Free education"],
    summary:
      "A free US educational site explaining stocks, bonds, ETFs, diversification, fees, compound growth and investment fraud.",
    steps: [
      "Open the website.",
      "Start with the basics of stocks and investing.",
      "Learn the difference between individual stocks and diversified funds.",
      "Study fees, risk tolerance and long-term investing.",
      "Use the resources to prepare before opening a brokerage account.",
    ],
    use: [
      "Build the basics before any real money is involved.",
      "Read about how fees and time shape a return.",
    ],
    caution:
      "Buying a company simply because it is popular can result in losses. Diversification helps spread risk but does not eliminate it.",
  },
  {
    name: "Investor.gov — Financial Calculators",
    url: "https://www.investor.gov/financial-tools-calculators",
    category: "Learn",
    tags: ["America", "Free education"],
    summary:
      "Financial calculators and educational tools for planning investments and understanding compound growth.",
    steps: [
      "Open the website.",
      "Select a relevant calculator.",
      "Enter a hypothetical initial amount and regular contributions.",
      "Test different return assumptions and investment periods.",
      "Compare the results while considering fees and inflation.",
    ],
    use: [
      "See how time and regular contributions compound.",
      "Compare what different assumptions do to a figure.",
    ],
    caution:
      "The calculator uses assumptions, not guaranteed returns. Actual investment performance may be lower than expected or negative.",
  },
  {
    name: "Capital Markets Authority Kenya",
    url: "https://www.cma.or.ke/investor-information/",
    category: "Check a provider",
    tags: ["Kenya", "Regulator"],
    summary:
      "Kenya's capital-markets regulator provides information to help investors understand regulated providers and investment risks.",
    steps: [
      "Open the website.",
      "Find investor education and protection resources.",
      "Check whether a broker, investment manager or other provider is authorised.",
      "Read the information about investor complaints and fraud prevention.",
      "Verify a provider independently before transferring money.",
    ],
    use: [
      "Confirm a provider is licensed before you send it anything.",
      "Learn what a complaint or a fraud report looks like.",
    ],
    benefit:
      "It can help you avoid fraudulent schemes, unlicensed operators and promises of guaranteed profits.",
    caution:
      "A licensed provider does not guarantee that your investments will make money.",
  },
  {
    name: "TradingView",
    url: "https://www.tradingview.com/",
    category: "Practise",
    tags: ["International", "Paper trading"],
    summary:
      "A charting and market-research platform with a paper-trading simulator that lets you practise without depositing real money.",
    steps: [
      "Open the website.",
      "Register for an account.",
      "Search for a company or stock ticker.",
      "Open its chart and locate the trading panel.",
      "Select Paper Trading if available and connect to the simulator.",
    ],
    use: [
      "Practise buying and selling with virtual funds.",
      "Record your entry price and exit price.",
      "Compare your results against a simple strategy.",
      "Learn how market orders and limit orders work before using real money.",
    ],
    caution:
      "Simulated success does not guarantee real profits. Emotions, trading costs and changing markets can affect real-world results.",
  },
  {
    name: "Nairobi Securities Exchange (NSE)",
    url: "https://www.nse.co.ke/",
    category: "Research",
    tags: ["Kenya"],
    summary:
      "The NSE is the marketplace for shares and other securities listed in Kenya.",
    steps: [
      "Open the website.",
      "Explore listed companies and market announcements.",
      "Research share prices and dividend information.",
      "Compare company performance and review relevant announcements.",
      "Use an eligible broker to place actual trades.",
    ],
    use: [
      "See which companies are listed and what they have announced.",
      "Look up prices and dividend history before you decide.",
    ],
    caution:
      "A company may report lower profits, reduce its dividends or face financial problems. You may also be unable to sell immediately at your desired price.",
  },
  {
    name: "SEC EDGAR",
    url: "https://www.sec.gov/edgar/search/",
    category: "Research",
    tags: ["America"],
    summary:
      "The US Securities and Exchange Commission's public database of company filings.",
    steps: [
      "Open the URL.",
      "Search for a company such as Apple, Microsoft or Amazon.",
      "Open its annual report, commonly Form 10-K.",
      "Review quarterly reports, commonly Form 10-Q.",
      "Examine revenue, net income, debt, cash flow and the risks the company discloses.",
    ],
    use: [
      "Read the official numbers rather than a social-media summary.",
      "Check what risks a company itself writes down.",
    ],
    benefit:
      "You can research companies using official filings rather than relying entirely on social-media recommendations.",
    caution:
      "Even a profitable company can become overpriced or experience unexpected problems. Research reduces uncertainty but cannot predict future prices.",
  },
  {
    name: "CDSC Kenya — Buying Kenyan shares",
    url: "https://cdsckenya.com/account-opening/",
    category: "Kenyan shares",
    tags: ["Kenya"],
    summary:
      "CDSC helps investors hold and manage shares traded on the Nairobi Securities Exchange (NSE). You can use its services to learn how to open a Central Depository System (CDS) account.",
    steps: [
      "Open the URL above.",
      "Read the account-opening instructions.",
      "Choose an authorised stockbroker or account-opening option.",
      "Provide the requested identification and personal details.",
      "Complete verification and follow the instructions for funding your trading account.",
    ],
    use: [
      "Research Kenyan companies, including banks and telecommunications businesses.",
      "Check share prices and company announcements.",
      "Buy or sell shares through your stockbroker or supported trading service.",
      "Keep your transaction records and account statements.",
    ],
    caution:
      "Share prices can fall, companies can perform poorly, and dividends are not guaranteed. Broker fees and taxes can also reduce returns.",
  },
  {
    name: "CDSC Kenya FAQ — Understand share ownership",
    url: "https://cdsckenya.com/faq/",
    category: "Kenyan shares",
    tags: ["Kenya"],
    summary:
      "Learn about CDS accounts, shareholding records and the role of stockbrokers in the Kenyan market.",
    steps: [
      "Open the FAQ page.",
      "Find answers about account opening, share ownership and transactions.",
      "Learn how to obtain statements and check your records.",
      "Contact your broker or CDSC through official channels if you find an unfamiliar transaction.",
    ],
    use: [
      "Understand what a CDS account actually holds for you.",
      "Know where to check that your records match reality.",
    ],
    benefit: "Your account records help you track your investments.",
    caution:
      "A CDS account does not prevent the market value of your shares from falling.",
  },
  {
    name: "Interactive Brokers — Buying American shares",
    url: "https://www.interactivebrokers.com/en/accounts/individual.php",
    category: "US & global shares",
    tags: ["America", "International"],
    summary:
      "An international brokerage platform that provides access to US and other international markets, subject to eligibility.",
    steps: [
      "Open the URL and choose an individual account.",
      "Enter your legal name, Kenyan address and requested personal details.",
      "Provide identification and tax-residency information.",
      "Wait for account approval.",
      "Check the available deposit methods, fees and currency-conversion costs before funding the account.",
    ],
    use: [
      "Search for companies such as Apple (AAPL), Microsoft (MSFT), Amazon (AMZN) and Nvidia (NVDA).",
      "Review their financial performance and share prices.",
      "Choose the number of shares or an eligible order size.",
      "Review the order and charges before submitting it.",
      "Monitor your portfolio without feeling pressured to trade daily.",
    ],
    caution:
      "Stock prices can drop substantially. Currency changes between USD and KSh may affect your returns. Avoid margin borrowing and leveraged products while learning.",
  },
  {
    name: "Trading 212 — Shares and ETFs",
    url: "https://www.trading212.com/",
    category: "US & global shares",
    tags: ["International"],
    summary:
      "A platform offering investing products in eligible countries. Availability depends on your country of residence.",
    steps: [
      "Open the website.",
      "Check whether new accounts are available to Kenyan residents.",
      "If eligible, register with your details.",
      "Complete identity verification.",
      "Read the fees, deposit rules and withdrawal conditions.",
    ],
    use: [
      "Research shares and exchange-traded funds (ETFs).",
      "Compare companies and diversified funds.",
      "Learn how recurring investments work, where available.",
      "Use the Invest account rather than leveraged CFD trading if your goal is long-term share ownership.",
    ],
    caution:
      "Your investments may decline in value. CFDs and leverage can magnify losses, so they are not suitable shortcuts to building wealth.",
  },
  {
    name: "Betika Kenya — Sports betting",
    url: "https://www.betika.com/en-ke/",
    category: "Betting",
    tags: ["Kenya"],
    summary: "A sports-betting platform for eligible users in Kenya.",
    steps: [
      "Open the official website.",
      "Check the current registration requirements and applicable age restrictions.",
      "If eligible, register using accurate details.",
      "Read the terms, deposit limits and withdrawal rules.",
      "Understand the odds and possible loss before placing a bet.",
    ],
    use: [
      "Read the odds and what each one actually pays before staking.",
      "Keep what you stake inside a limit you had already set.",
    ],
    caution:
      "A losing bet can cost you the entire amount staked. Betting is not investing, and it should never be treated as a dependable income source.",
  },
  {
    name: "Aviator — Crash-style gambling game",
    url: "https://www.betika.com/en-ke/aviator/",
    category: "Betting",
    tags: ["Kenya", "Gambling"],
    summary:
      "A crash-style game in which a multiplier rises and the round can end unexpectedly.",
    steps: [
      "Open the link and check whether the game is currently available.",
      "Read the rules and payout conditions before participating.",
      "Understand that a round may end before you choose to cash out.",
      "Never increase your stake to recover a previous loss.",
    ],
    use: [
      "Treat any stake as money you have already decided to lose.",
      "Stop when you reach that limit, not when the game tempts you on.",
    ],
    caution:
      "You can lose your entire stake in one round. Previous multipliers do not reliably predict the next result. There is no guaranteed strategy for making money from Aviator.",
  },
];

/** One hypothetical walk for a fixed stake, so a swing reads as a number rather
 * than a feeling. The arithmetic is exact and pre-computed - it is a worked
 * example, never a prediction, and it rests on no one's current prices. */
export interface ExampleOutcome {
  movement: string;
  value_after: string;
  change: string;
  direction: "gain" | "loss";
}

export const EXAMPLE_STAKE = "KSh 5,000";
export const EXAMPLE_OUTCOMES: ExampleOutcome[] = [
  { movement: "+20%", value_after: "KSh 6,000", change: "+KSh 1,000", direction: "gain" },
  { movement: "+10%", value_after: "KSh 5,500", change: "+KSh 500", direction: "gain" },
  { movement: "−10%", value_after: "KSh 4,500", change: "−KSh 500", direction: "loss" },
  { movement: "−30%", value_after: "KSh 3,500", change: "−KSh 1,500", direction: "loss" },
  { movement: "−100%", value_after: "KSh 0", change: "−KSh 5,000", direction: "loss" },
];

export const EXAMPLE_NOTE =
  "These are hypothetical calculations before fees, taxes and currency changes, not predictions.";

export const STARTING_ORDER =
  "A sensible order: learn through the CMA and Investor.gov, practise through TradingView, research companies through the NSE or SEC EDGAR, and only then consider investing through a regulated provider that accepts Kenyan residents. Keep your essential living and university money separate from investment funds.";
