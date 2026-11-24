
const features = [
  {
    number: "01",
    title: "Find better leads",
    description:
      "Discover potential customers and businesses that match your ideal customer profile.",
    icon: "◎",
  },
  {
    number: "02",
    title: "Research businesses",
    description:
      "Get useful business insights and information without spending hours researching.",
    icon: "⌕",
  },
  {
    number: "03",
    title: "Create outreach",
    description:
      "Generate personalized outreach messages that help you start meaningful conversations.",
    icon: "↗",
  },
  {
    number: "04",
    title: "Grow your pipeline",
    description:
      "Keep your prospects, research and outreach organized in one intelligent workspace.",
    icon: "▥",
  },
];

const suggestions = [
  "Find potential customers",
  "Research a business",
  "Draft an outreach email",
];

function ArrowIcon() {
  return <span aria-hidden="true">↗</span>;
}

function ProductPreview() {
  return (
    <div className="preview-window">
      <div className="preview-topbar">
        <div className="flex items-center gap-2">
          <span className="brand-mark small">o</span>
          <span className="font-semibold text-slate-800">outrivo</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="status-dot" />
          <span className="text-xs text-slate-500">AI ready</span>
          <div className="avatar">M</div>
        </div>
      </div>

      <div className="preview-body">
        <aside className="preview-sidebar">
          <div className="sidebar-action">＋ New conversation</div>
          <p className="sidebar-label">WORKSPACE</p>
          <div className="sidebar-link active">◈ Overview</div>
          <div className="sidebar-link">◎ Find leads</div>
          <div className="sidebar-link">⌕ Research</div>
          <div className="sidebar-link">↗ Outreach</div>
          <div className="sidebar-link">▤ Conversations</div>
          <div className="sidebar-bottom">⚙ Settings</div>
        </aside>

        <div className="preview-chat">
          <div className="preview-greeting">
            <span className="eyebrow">YOUR AI BUSINESS ASSISTANT</span>
            <h3>What can I help you achieve?</h3>
            <p>
              Find opportunities, research businesses and build your pipeline.
            </p>
          </div>

          <div className="chat-message user-message">
            Find me potential dental clinics in Lahore for outreach.
          </div>

          <div className="assistant-message">
            <div className="assistant-avatar">o</div>
            <div>
              <strong>Here's how we can get started.</strong>
              <p>
                I'll help you identify relevant dental clinics, research their
                businesses and prepare personalized outreach.
              </p>
              <div className="result-tags">
                <span>Lead discovery</span>
                <span>Business research</span>
              </div>
            </div>
          </div>

          <div className="preview-input">
            <span>Ask Outrivo anything...</span>
            <span className="send-button">↑</span>
          </div>
          <p className="preview-disclaimer">
            Outrivo can make mistakes. Review important information.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <a href="/" className="brand" aria-label="Outrivo home">
          <span className="brand-mark">o</span>
          <span>outrivo<span className="brand-period">.</span></span>
        </a>

        <nav className="desktop-nav">
          <a href="#features">Features</a>
          <a href="#how-it-works">How it works</a>
          <a href="#about">About</a>
        </nav>

        <div className="header-actions">
          <a href="/login" className="login-link">Log in</a>
          <a href="/signup" className="button button-dark header-cta">
            Get started <ArrowIcon />
          </a>
        </div>
      </header>

      <section className="hero-section">
        <div className="hero-glow" />
        <div className="hero-content">
          <div className="announcement">
            <span className="announcement-dot" />
            YOUR BUSINESS, WITH AN AI ADVANTAGE
            <span>↗</span>
          </div>

          <h1>
            Less searching.
            <br />
            More <span className="gradient-text">growing.</span>
          </h1>

          <p className="hero-description">
            Meet your AI-powered business assistant. Find leads, research
            companies and create personalized outreach — all from one place.
          </p>

          <div className="hero-actions">
            <a href="/signup" className="button button-dark">
              Start with Outrivo <ArrowIcon />
            </a>
            <a href="#features" className="button button-light">
              Explore features
            </a>
          </div>

          <div className="hero-note">
            <span>✦</span> Your smarter way to find and connect with customers.
          </div>
        </div>

        <div className="hero-preview">
          <div className="preview-decoration decoration-one" />
          <div className="preview-decoration decoration-two" />
          <ProductPreview />
        </div>

        <div className="hero-bottom">
          <span>ONE WORKSPACE</span>
          <span className="hero-bottom-line" />
          <span>MORE POSSIBILITIES</span>
        </div>
      </section>

      <section className="intro-section" id="about">
        <span className="eyebrow">MEET YOUR NEW WORKFLOW</span>
        <h2>
          Everything you need to move
          <br className="desktop-break" /> your business <span>forward.</span>
        </h2>
        <p>
          Stop switching between tools and repetitive tasks. Let one intelligent
          assistant help you turn research into relationships and opportunities
          into customers.
        </p>
      </section>

      <section className="features-section" id="features">
        <div className="section-heading">
          <div>
            <span className="eyebrow">BUILT FOR MOMENTUM</span>
            <h2>Meet your business toolkit.</h2>
          </div>
          <p>
            From the first prospect to the first conversation, Outrivo helps
            you make every step count.
          </p>
        </div>

        <div className="feature-grid">
          {features.map((feature) => (
            <article className="feature-card" key={feature.number}>
              <div className="feature-card-top">
                <span className="feature-icon">{feature.icon}</span>
                <span className="feature-number">{feature.number}</span>
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
              <a href="/signup" className="feature-link">
                Explore feature <ArrowIcon />
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="workflow-section" id="how-it-works">
        <div className="workflow-copy">
          <span className="eyebrow">SIMPLE BY DESIGN</span>
          <h2>
            Your next big opportunity starts with a <span>conversation.</span>
          </h2>
          <p>
            Just tell Outrivo what you're trying to achieve. Your AI assistant
            helps you research, discover and prepare the next step.
          </p>
          <a href="/signup" className="button button-dark">
            Try Outrivo <ArrowIcon />
          </a>
        </div>

        <div className="workflow-card">
          <div className="workflow-card-header">
            <span className="brand-mark small">o</span>
            <div>
              <strong>Start with a simple request</strong>
              <p>Tell Outrivo what you need.</p>
            </div>
          </div>

          {suggestions.map((suggestion, index) => (
            <div className="suggestion-row" key={suggestion}>
              <span>{["◎", "⌕", "↗"][index]}</span>
              {suggestion}
              <span className="suggestion-arrow">↗</span>
            </div>
          ))}

          <div className="workflow-input">
            <span>What would you like to work on?</span>
            <span className="send-button">↑</span>
          </div>
          <p className="workflow-caption">A smarter way to get things moving.</p>
        </div>
      </section>

      <section className="cta-section">
        <div className="cta-orb" />
        <span className="eyebrow">YOUR NEXT MOVE STARTS HERE</span>
        <h2>
          Ready to work
          <br />
          <span>smarter?</span>
        </h2>
        <p>
          Bring your business goals. Let Outrivo help you take the next step.
        </p>
        <a href="/signup" className="button button-white">
          Get started with Outrivo <ArrowIcon />
        </a>
      </section>

      <footer className="site-footer">
        <a href="/" className="brand">
          <span className="brand-mark">o</span>
          <span>outrivo<span className="brand-period">.</span></span>
        </a>
        <p>Intelligence for your next opportunity.</p>
        <span className="copyright">© 2026 Outrivo. All rights reserved.</span>
      </footer>
    </main>
  );
}
