// Nav-as-data. Meridian design = one "Workspace" group of 8 screens.
export type NavItem = { href: string; label: string; icon?: string; blurb?: string };
export const NAV: NavItem[] = [
  { href: '/',            label: 'Overview',          blurb: 'CFC bakery demand — the whole picture' },
  { href: '/workflow',    label: 'Workflow',          blurb: 'The whole pipeline, live — data → train → approve → serve' },
  { href: '/data',        label: 'Data Explorer',     blurb: 'Sources, gaps, and demand structure' },
  { href: '/eda',         label: 'Demand EDA',        blurb: 'Plain-language look at the sales history — seasons, top products, freshness' },
  { href: '/experiments/run', label: 'Run Experiment', blurb: 'Launch the full pipeline live — extract→train→backtest→deploy' },
  { href: '/leaderboard', label: 'Model Leaderboard', blurb: 'Every model, ranked by WMAPE on identical folds' },
  { href: '/results',     label: 'Model Evidence',    blurb: 'Calibration, residuals, feature importance, segments' },
  { href: '/network',     label: 'Forecast Dashboard', blurb: 'Per outlet × product, quantile forecast' },
  { href: '/ordering',    label: 'Smart Ordering',    blurb: 'Newsvendor order policy and picklist' },
  { href: '/accuracy',    label: 'Accuracy',          blurb: 'Daily forecast vs actual — how close we are, and the trend' },
  { href: '/learning',    label: 'Monitoring',        blurb: 'Feature drift (PSI), retraining, pipeline health' },
  { href: '/deploy',      label: 'Deploy & API',      blurb: 'Versions, endpoint, integration' }
];
