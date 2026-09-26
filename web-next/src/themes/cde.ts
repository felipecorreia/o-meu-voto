/**
 * CDE 2026 identity on top of two real Astryx themes.
 *
 * Both variants share the same identity tokens (navy accent, TSE portal neutrals, the four
 * CDE mark colours as categorical families, Inter at weight 500 for headings). What differs
 * is the base theme they extend: `matcha` brings organic shapes (pill buttons, 18px containers,
 * 6px spacing scale) and CDE green as the secondary highlight; `butter` brings squarer shapes
 * (8px/12px) and CDE gold as the secondary highlight. Nothing here forks component source:
 * everything is `defineTheme({extends})` token and component overrides.
 *
 * Palette source: data/bre-design-astryx/palette-cde-2026.md (captain, 2026-09-25).
 * Accessibility rules of its section 8: gold and CDE blue are never text on white; small text
 * on green uses #1F7F47; text variants of the mark colours are darkened until >= 4.5:1 on
 * white and on their own tint (checked with a WCAG script, see report.md).
 */
import {defineTheme} from '@astryxdesign/core/theme';
import {matchaTheme} from './matcha/matchaTheme';
import {butterTheme} from './butter/butterTheme';

// ---- CDE / TSE portal palette (hex as supplied) --------------------------------------------
export const cde = {
  graphite: '#414042',
  gold: '#E6B10F',
  blue: '#348AAB',
  green: '#558530',
  navy950: '#0C2345',
  navy900: '#132344',
  navy700: '#1B305A',
  navy500: '#586C98',
  navy300: '#5E83BA',
  navyHover: '#163058',
  inkDeep: '#061937',
  link: '#1A5FB4',
  yellow500: '#FFDA59',
  yellow600: '#E8C230',
  yellowBorder: '#CCAE47',
  yellow200: '#F5E4A3',
  orange500: '#EF8F20',
  green600: '#29A35C',
  green400: '#47C77D',
  green200: '#82D9A7',
  greenText: '#1F7F47', // small text on green: section 8
  danger: '#CD201F',
  bg: '#F5F5F5',
  bgCool: '#E6ECF0',
  surface: '#FFFFFF',
  surfaceAlt: '#F2F3F5',
  surfaceSunk: '#DCDCDC',
  text: '#0A0A0A',
  textBody: '#222222',
  textMuted: '#6B6B6B',
  textSecondary: '#546483', // rgba(27,48,90,.75) flattened on white
  border: '#00000020', // rgba(0,0,0,.125)
  borderStrong: '#0000002D', // rgba(0,0,0,.176)
  borderLight: '#DEE2E6',
  wave1: '#CDE2EA',
  wave2: '#D8E8F0',
  wave3: '#E8F0F8',
  wave4: '#F0F8F8',
} as const;

// Darkened text variants of the mark colours (>= 4.5:1 on white and on the 20% tint).
const markText = {
  blue: '#175A74',
  green: '#3E6423',
  yellow: '#7A5E00',
  orange: '#8A4E0A',
  gray: cde.graphite,
} as const;

type DefineThemeInput = Parameters<typeof defineTheme>[0];
type Tokens = NonNullable<DefineThemeInput['tokens']>;

/** Identity tokens shared by both variants. Dark values exist so `mode="system"` never
 *  breaks, but the product ships light-only (the captain rejects dark themes). */
const identityTokens: Tokens = {
  // Core semantic
  '--color-accent': [cde.navy700, '#9DB4E0'],
  '--color-accent-muted': [`${cde.navy700}14`, '#9DB4E024'],
  '--color-on-accent': ['#FFFFFF', cde.navy950],
  '--color-neutral': [`${cde.navy700}0F`, '#FFFFFF14'],
  '--color-background-body': [cde.bg, '#0F1A2E'],
  '--color-background-surface': [cde.surface, '#16233B'],
  '--color-background-card': [cde.surface, '#16233B'],
  '--color-background-popover': [cde.surface, '#1B2A45'],
  '--color-background-muted': [cde.bgCool, '#1B2A45'],
  '--color-background-inverted': [cde.navy700, '#E6ECF0'],
  '--color-overlay': [`${cde.navy950}80`, `${cde.navy950}CC`],
  '--color-overlay-hover': [`${cde.navy700}0D`, '#FFFFFF0D'],
  '--color-overlay-pressed': [`${cde.navy700}1A`, '#FFFFFF1A'],

  // Text and icons: navy is the TSE body colour; secondary is navy at 75%.
  '--color-text-primary': [cde.navy700, '#E6ECF0'],
  '--color-text-secondary': [cde.textSecondary, '#9DB4E0'],
  '--color-text-disabled': ['#8A94A8', '#5A6A8A'],
  '--color-text-accent': [cde.navy700, '#9DB4E0'],
  '--color-on-dark': '#FFFFFF',
  '--color-on-light': cde.navy700,
  '--color-icon-accent': [cde.navy700, '#9DB4E0'],
  '--color-icon-primary': [cde.navy700, '#E6ECF0'],
  '--color-icon-secondary': [cde.textSecondary, '#9DB4E0'],
  '--color-icon-disabled': ['#8A94A8', '#5A6A8A'],

  // Status. Success is the TSE CTA green darkened for small text (section 8).
  '--color-success': [cde.greenText, cde.green200],
  '--color-success-muted': [`${cde.green600}26`, `${cde.green200}26`],
  '--color-on-success': ['#FFFFFF', cde.navy950],
  '--color-error': [cde.danger, '#FF8A80'],
  '--color-error-muted': [`${cde.danger}1F`, '#FF8A8026'],
  '--color-on-error': ['#FFFFFF', cde.navy950],
  // Warning follows the TSE notice band: yellow surface, deep-ink text.
  '--color-warning': [cde.yellowBorder, cde.yellow500],
  '--color-warning-muted': [cde.yellow500, `${cde.yellow500}33`],
  '--color-on-warning': [cde.inkDeep, cde.navy950],

  // Borders: thin, translucent, almost no shadow (section 4).
  '--color-border': [cde.border, '#FFFFFF1A'],
  '--color-border-emphasized': [cde.borderStrong, '#FFFFFF33'],
  '--color-skeleton': [cde.surfaceSunk, '#2A3A57'],
  '--color-shadow': ['#0000000D', '#00000066'],
  '--shadow-low': '0 4px 13px 1px rgba(0,0,0,.05)',
  '--shadow-med': '0 4px 13px 1px rgba(0,0,0,.05)',
  '--shadow-high': '0 6px 18px 2px rgba(0,0,0,.08)',

  // Categorical families = the four CDE mark colours (+ the warm wave orange). Used for
  // neutral metrics and section accents only; never mapped to parties (palette section 7).
  '--color-background-blue': [`${cde.blue}33`, `${cde.blue}40`],
  '--color-border-blue': [cde.blue, cde.blue],
  '--color-icon-blue': [markText.blue, '#8FCBE0'],
  '--color-text-blue': [markText.blue, '#8FCBE0'],
  '--color-background-green': [`${cde.green}33`, `${cde.green}40`],
  '--color-border-green': [cde.green, cde.green],
  '--color-icon-green': [markText.green, '#B5D48F'],
  '--color-text-green': [markText.green, '#B5D48F'],
  '--color-background-yellow': [`${cde.gold}40`, `${cde.gold}40`],
  '--color-border-yellow': [cde.gold, cde.gold],
  '--color-icon-yellow': [markText.yellow, '#F2D27A'],
  '--color-text-yellow': [markText.yellow, '#F2D27A'],
  '--color-background-orange': [`${cde.orange500}33`, `${cde.orange500}40`],
  '--color-border-orange': [cde.orange500, cde.orange500],
  '--color-icon-orange': [markText.orange, '#F5B87A'],
  '--color-text-orange': [markText.orange, '#F5B87A'],
  '--color-background-gray': [`${cde.graphite}1F`, '#FFFFFF1F'],
  '--color-border-gray': [cde.graphite, '#9AA0A6'],
  '--color-icon-gray': [markText.gray, '#C8CCD2'],
  '--color-text-gray': [markText.gray, '#C8CCD2'],
};

const inter = {
  family: 'Inter',
  fallbacks: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
};

/** Inter everywhere; large headings at weight 500, never bold (palette section 3). */
const typography: DefineThemeInput['typography'] = {
  scale: {base: 16, ratio: 1.25},
  body: inter,
  heading: {...inter, weight: 'medium', weights: {1: 'medium', 2: 'medium', 3: 'medium', 4: 'medium', 5: 'semibold', 6: 'semibold'}},
  code: {family: 'JetBrains Mono', fallbacks: '"SF Mono", Monaco, Consolas, monospace'},
};

const motion = {fast: 125, medium: 300, slow: 700, ratio: 0.75};

// ---- Variant A: matcha base ----------------------------------------------------------------
// Keeps matcha's organic geometry (pill buttons, spacing scale, 18px containers) and uses CDE
// green as the secondary highlight, like the TSE's green CTA.
export const cdeMatchaTheme = defineTheme({
  name: 'cde-matcha',
  extends: matchaTheme,
  typography,
  motion,
  tokens: {
    ...identityTokens,
    '--radius-inner': '8px',
    '--radius-element': '12px',
    '--radius-container': '18px',
    '--radius-page': '28px',
    // The base theme's sage borders become the hero-wave tint, so cards sit on a cool halo.
    '--color-border': [cde.borderLight, '#FFFFFF1A'],
    '--color-background-muted': [cde.wave3, '#1B2A45'],
  },
  components: {
    button: {
      base: {borderRadius: 'var(--radius-full)', fontWeight: 'var(--font-weight-semibold)'},
      'variant:secondary': {
        backgroundColor: 'transparent',
        borderWidth: '1.5px',
        borderStyle: 'solid',
        borderColor: `light-dark(${cde.navy700}, #9DB4E0)`,
        color: `light-dark(${cde.navy700}, #9DB4E0)`,
        ':hover': {backgroundColor: `light-dark(${cde.navy700}14, #9DB4E014)`},
      },
    },
    card: {base: {borderRadius: 'var(--radius-container)', padding: 'var(--spacing-3)'}},
    badge: {
      'variant:success': {backgroundColor: cde.greenText, color: '#FFFFFF'},
      'variant:warning': {backgroundColor: cde.yellow500, color: cde.inkDeep},
      'variant:info': {backgroundColor: cde.wave1, color: cde.navy700},
    },
    'top-nav': {base: {backgroundColor: 'light-dark(#FFFFFF, #16233B)', borderBottom: `1px solid ${cde.borderLight}`}},
    'top-nav-heading': {base: {color: cde.navy700, '--color-text-primary': cde.navy700}},
    'top-nav-item': {
      base: {color: cde.textSecondary},
      selected: {color: cde.navy700, backgroundColor: `${cde.green}1F`},
    },
    'selectable-card': {
      selected: {borderColor: cde.green, backgroundColor: `${cde.green}14`, boxShadow: `inset 0 0 0 2px ${cde.green}`},
    },
  },
});

// ---- Variant B: butter base ----------------------------------------------------------------
// Keeps butter's squarer geometry and vivid semantic fills, redirects its blue accent to CDE
// navy and its buttery yellows to the TSE notice-band gold.
export const cdeButterTheme = defineTheme({
  name: 'cde-butter',
  extends: butterTheme,
  typography,
  motion,
  tokens: {
    ...identityTokens,
    '--text-supporting-size': '13px',
    '--radius-inner': '4px',
    '--radius-element': '6px',
    '--radius-container': '8px',
    '--radius-page': '16px',
    '--color-background-muted': [cde.yellow200, '#1B2A45'],
  },
  components: {
    'top-nav': {base: {backgroundColor: 'light-dark(#FFFFFF, #16233B)', borderBottom: `2px solid ${cde.yellow500}`}},
    'top-nav-heading': {base: {color: cde.navy700, '--color-text-primary': cde.navy700}},
    'top-nav-item': {
      base: {color: cde.textSecondary},
      selected: {color: cde.navy700, backgroundColor: cde.yellow200, ':hover': {backgroundColor: cde.yellow200}},
    },
    button: {
      base: {paddingBlock: 'var(--spacing-2)', paddingInline: 'var(--spacing-4)', fontWeight: 'var(--font-weight-semibold)'},
      'variant:secondary': {
        backgroundColor: 'transparent',
        borderWidth: '1.5px',
        borderStyle: 'solid',
        borderColor: `light-dark(${cde.navy700}, #9DB4E0)`,
        color: `light-dark(${cde.navy700}, #9DB4E0)`,
        ':hover': {backgroundColor: `light-dark(${cde.navy700}14, #9DB4E014)`},
      },
      'variant:ghost': {color: `light-dark(${cde.navy700}, #9DB4E0)`},
      'variant:destructive': {backgroundColor: `${cde.danger}1F`, color: cde.danger},
    },
    badge: {
      base: {height: '28px', paddingBlock: '0', paddingInline: 'var(--spacing-3)'},
      'variant:info': {backgroundColor: cde.navy500, color: '#FFFFFF'},
      'variant:neutral': {backgroundColor: cde.yellow200, color: cde.navy700},
      'variant:success': {backgroundColor: cde.greenText, color: '#FFFFFF'},
      'variant:warning': {backgroundColor: cde.yellow500, color: cde.inkDeep},
      'variant:error': {backgroundColor: cde.danger, color: '#FFFFFF'},
    },
    banner: {
      'status:info': {'--color-accent-muted': cde.bgCool, '--color-text-primary': cde.navy700, '--color-text-secondary': cde.navy700, '--color-accent': cde.navy700},
      'status:success': {'--color-success-muted': cde.green200, '--color-text-primary': cde.navy950, '--color-text-secondary': cde.navy950, '--color-success': cde.navy950},
      'status:warning': {'--color-warning-muted': cde.yellow500, '--color-text-primary': cde.inkDeep, '--color-text-secondary': cde.inkDeep, '--color-warning': cde.inkDeep},
      'status:error': {'--color-error-muted': cde.danger, '--color-text-primary': '#FFFFFF', '--color-text-secondary': '#FFFFFF', '--color-error': '#FFFFFF'},
    },
    'progress-bar-fill': {'variant:success': {backgroundColor: cde.green600}, 'variant:warning': {backgroundColor: cde.yellow600}, 'variant:error': {backgroundColor: cde.danger}},
    'field-status': {
      'type:success': {backgroundColor: cde.green200, color: cde.navy950},
      'type:warning': {backgroundColor: cde.yellow500, color: cde.inkDeep},
      'type:error': {backgroundColor: cde.danger, color: '#FFFFFF'},
    },
    'text-input': {'status:success': {'--color-success': cde.greenText}, 'status:warning': {'--color-warning': cde.yellowBorder}, 'status:error': {'--color-error': cde.danger}},
    selector: {'status:success': {'--color-success': cde.greenText}, 'status:warning': {'--color-warning': cde.yellowBorder}, 'status:error': {'--color-error': cde.danger}},
    typeahead: {'status:success': {'--color-success': cde.greenText}, 'status:warning': {'--color-warning': cde.yellowBorder}, 'status:error': {'--color-error': cde.danger}},
    'selectable-card': {
      selected: {borderColor: cde.yellowBorder, backgroundColor: cde.yellow200, boxShadow: `inset 0 0 0 2px ${cde.yellowBorder}`},
    },
    // Butter's Sarina display font is off-brand here: Inter for display sizes too.
    text: {
      'type:display-1': {fontFamily: 'var(--font-family-heading)'},
      'type:display-2': {fontFamily: 'var(--font-family-heading)'},
      'type:display-3': {fontFamily: 'var(--font-family-heading)'},
    },
  },
});

export type VariantName = 'matcha' | 'butter';
export const variants: Record<VariantName, {theme: typeof cdeMatchaTheme; label: string; blurb: string}> = {
  matcha: {theme: cdeMatchaTheme, label: 'Matcha + CDE', blurb: 'formas orgânicas, verde CDE como destaque'},
  butter: {theme: cdeButterTheme, label: 'Butter + CDE', blurb: 'formas retas, dourado CDE como destaque'},
};

// ---- Tela 1 (Comparar, choice mode) tokens ---------------------------------------------------
// The redesigned choice screen (spec: Tela 1, section 4.1) on the Butter + CDE theme. Applied as
// CSS custom properties on the page container by `ComparePage` and read by `styles.css` as
// `var(--cv-*)`, so no component carries a loose hex. Green is choice and action, yellow the
// highlight, petrol blue the support colour, navy the text. The tray avatars take their colour
// from the ORDER OF MARKING (slot 1 blue, 2 strong green, 3 yellow with navy text, 4 navy),
// never from the candidacy or the party (ADR 0008); see `.tray-av[data-slot]` in styles.css.
export const pickTokens = {
  '--cv-ink': '#1A2233',
  '--cv-ink-2': '#4A5263',
  '--cv-ink-3': '#5B6374',
  '--cv-navy': cde.navy700,
  '--cv-green': cde.green,
  '--cv-green-strong': '#467025',
  '--cv-green-tint': '#F4F8EF',
  '--cv-green-halo': 'rgba(85,133,48,.14)',
  '--cv-yellow': cde.yellow500,
  '--cv-yellow-tint': '#FFF1C2',
  '--cv-blue': '#2A6F8A',
  '--cv-surface': '#F2F3F6',
  '--cv-line': '#E6E8ED',
  '--cv-line-2': '#E4E6EB',
  '--cv-line-tray': '#ECEEF2',
  '--cv-check-off': '#B9BFCA',
  '--cv-avatar-bg': '#EDF0F5',
  '--cv-cta-off': '#EEF0F3',
  '--cv-chip-line': '#DADDE3',
  '--cv-empty-bg': '#F7F8FA',
} as const;
