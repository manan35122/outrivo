
import Link from "next/link";

const navigation = [
  { label: "Dashboard", href: "/dashboard", icon: "▦", active: true },
  { label: "AI Assistant", href: "/assistant", icon: "✦" },
  { label: "Leads", href: "/leads", icon: "◎" },
  { label: "Outreach", href: "/outreach", icon: "↗" },
  { label: "History", href: "/history", icon: "◷" },
];

const activities = [
  {
    title: "New leads discovered",
    description: "12 potential customers added to your pipeline",
    time: "10 minutes ago",
    icon: "◎",
  },
  {
    title: "Outreach draft created",
    description: "A new email draft was prepared for review",
    time: "35 minutes ago",
    icon: "✉",
  },
  {
    title: "Lead status updated",
    description: "A lead moved to the Contacted stage",
    time: "1 hour ago",
    icon: "↗",
  },
];

const stats = [
  {
    label: "Total leads",
    value: "128",
    change: "+12 this week",
    icon: "◎",
  },
  {
    label: "Outreach drafts",
    value: "36",
    change: "8 awaiting review",
    icon: "✉",
  },
  {
    label: "Meetings booked",
    value: "14",
    change: "+3 this week",
    icon: "▣",
  },
  {
    label: "Conversion rate",
    value: "8.4%",
    change: "Demo metric",
    icon: "↗",
  },
];

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-[#f8f8fc] text-[#17152b]">
      <div className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="hidden w-[250px] shrink-0 border-r border-[#eceaf3] bg-white px-5 py-7 md:flex md:flex-col">
          <Link href="/" className="mb-12 flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#7060df] text-lg font-bold text-white">
              O
            </div>
            <span className="text-xl font-bold tracking-tight">
              outrivo
            </span>
          </Link>

          <p className="mb-4 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#9995aa]">
            Workspace
          </p>

          <nav className="space-y-1">
            {navigation.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${
                  item.active
                    ? "bg-[#f0edff] text-[#6957d7]"
                    : "text-[#777389] hover:bg-[#f7f6fb] hover:text-[#29253d]"
                }`}
              >
                <span className="w-5 text-center text-lg">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="mt-auto rounded-2xl border border-[#eeeafa] bg-[#faf9ff] p-4">
            <div className="mb-2 text-sm font-semibold">
              Need assistance?
            </div>
            <p className="mb-3 text-xs leading-5 text-[#858198]">
              Let your AI assistant help you manage your sales workflow.
            </p>
            <Link
              href="/assistant"
              className="block rounded-lg bg-[#7060df] px-3 py-2 text-center text-xs font-semibold text-white transition hover:bg-[#5e4dcc]"
            >
              Open assistant
            </Link>
          </div>

          <div className="mt-6 border-t border-[#eeeaf3] pt-5">
            <Link
              href="/settings"
              className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm text-[#777389] hover:bg-[#f7f6fb]"
            >
              <span className="text-lg">⚙</span>
              Settings
            </Link>
            <div className="mt-4 flex items-center gap-3 px-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#e9e4ff] text-sm font-bold text-[#6957d7]">
                U
              </div>
              <div>
                <p className="text-sm font-semibold">Workspace user</p>
                <p className="text-xs text-[#9692a5]">Outrivo workspace</p>
              </div>
            </div>
          </div>
        </aside>

        {/* Main content */}
        <main className="min-w-0 flex-1">
          <header className="flex h-[76px] items-center justify-between border-b border-[#eceaf3] bg-white px-5 sm:px-8">
            <div>
              <p className="text-xs text-[#9692a5]">Workspace / Overview</p>
              <h1 className="text-lg font-bold">Dashboard</h1>
            </div>

            <div className="flex items-center gap-3">
              <span className="hidden rounded-full bg-[#f0edff] px-3 py-1.5 text-xs font-medium text-[#6957d7] sm:inline-flex">
                Demo workspace
              </span>
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#e9e4ff] font-semibold text-[#6957d7]">
                U
              </div>
            </div>
          </header>

          <div className="mx-auto max-w-[1400px] px-5 py-8 sm:px-8">
            {/* Welcome */}
            <section className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-center">
              <div>
                <p className="mb-2 text-sm font-medium text-[#7060df]">
                  YOUR BUSINESS AT A GLANCE
                </p>
                <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
                  Welcome to Outrivo
                </h2>
                <p className="mt-2 text-sm text-[#858198]">
                  Manage your leads, outreach, and sales with your AI assistant.
                </p>
              </div>

              <Link
                href="/assistant"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#7060df] px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[#5e4dcc]"
              >
                <span>✦</span>
                Talk to AI assistant
              </Link>
            </section>

            {/* Statistics */}
            <section className="mb-8">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-base font-bold">Performance overview</h3>
                <span className="text-xs text-[#9995aa]">
                  Sample dashboard data
                </span>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {stats.map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-2xl border border-[#eceaf3] bg-white p-5 shadow-[0_2px_12px_rgba(30,20,70,0.025)]"
                  >
                    <div className="mb-5 flex items-center justify-between">
                      <p className="text-sm text-[#858198]">
                        {stat.label}
                      </p>
                      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#f1eeff] text-lg text-[#7060df]">
                        {stat.icon}
                      </span>
                    </div>
                    <p className="text-3xl font-bold tracking-tight">
                      {stat.value}
                    </p>
                    <p className="mt-2 text-xs text-[#8b85a0]">
                      {stat.change}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            {/* Main grid */}
            <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
              {/* Activity */}
              <section className="rounded-2xl border border-[#eceaf3] bg-white p-5 sm:p-6">
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h3 className="font-bold">Recent activity</h3>
                    <p className="mt-1 text-xs text-[#9692a5]">
                      What's happening in your workspace
                    </p>
                  </div>
                  <Link
                    href="/history"
                    className="text-xs font-semibold text-[#7060df] hover:underline"
                  >
                    View history
                  </Link>
                </div>

                <div className="space-y-5">
                  {activities.map((activity, index) => (
                    <div key={activity.title} className="flex gap-4">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#f1eeff] text-lg text-[#7060df]">
                        {activity.icon}
                      </div>
                      <div className="min-w-0 flex-1 border-b border-[#f0eef5] pb-5 last:border-0 last:pb-0">
                        <div className="flex flex-col justify-between gap-1 sm:flex-row">
                          <p className="text-sm font-semibold">
                            {activity.title}
                          </p>
                          <span className="text-xs text-[#a09bad]">
                            {activity.time}
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-5 text-[#858198]">
                          {activity.description}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Quick actions */}
              <section className="rounded-2xl border border-[#eceaf3] bg-white p-5 sm:p-6">
                <h3 className="font-bold">Quick actions</h3>
                <p className="mt-1 text-xs text-[#9692a5]">
                  Get things done faster
                </p>

                <div className="mt-6 space-y-3">
                  <Link
                    href="/assistant"
                    className="flex items-center gap-4 rounded-xl border border-[#eeeaf5] p-4 transition hover:border-[#cfc7ff] hover:bg-[#faf9ff]"
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f0edff] text-lg text-[#7060df]">
                      ✦
                    </span>
                    <span>
                      <span className="block text-sm font-semibold">
                        Ask your AI agent
                      </span>
                      <span className="mt-1 block text-xs text-[#9692a5]">
                        Find leads and manage your workflow
                      </span>
                    </span>
                  </Link>

                  <Link
                    href="/leads"
                    className="flex items-center gap-4 rounded-xl border border-[#eeeaf5] p-4 transition hover:border-[#cfc7ff] hover:bg-[#faf9ff]"
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f0edff] text-lg text-[#7060df]">
                      ◎
                    </span>
                    <span>
                      <span className="block text-sm font-semibold">
                        Manage leads
                      </span>
                      <span className="mt-1 block text-xs text-[#9692a5]">
                        Review your sales pipeline
                      </span>
                    </span>
                  </Link>

                  <Link
                    href="/outreach"
                    className="flex items-center gap-4 rounded-xl border border-[#eeeaf5] p-4 transition hover:border-[#cfc7ff] hover:bg-[#faf9ff]"
                  >
                    <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#f0edff] text-lg text-[#7060df]">
                      ↗
                    </span>
                    <span>
                      <span className="block text-sm font-semibold">
                        Review outreach
                      </span>
                      <span className="mt-1 block text-xs text-[#9692a5]">
                        Check and approve message drafts
                      </span>
                    </span>
                  </Link>
                </div>
              </section>
            </div>

            <p className="mt-8 text-center text-xs text-[#aaa6b5]">
              Outrivo · Your AI-powered business assistant
            </p>
          </div>
        </main>
      </div>
    </div>
  );
}
