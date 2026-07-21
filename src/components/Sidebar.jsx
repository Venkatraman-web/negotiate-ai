import { Link, useLocation } from 'react-router-dom'
import {
  BarChart3,
  FileText,
  LayoutDashboard,
  MessageCircleMore,
  Settings,
  Sparkles,
  UserRound,
} from 'lucide-react'

const items = [
  { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { label: 'New Session', path: '/negotiation', icon: MessageCircleMore },
  { label: 'Previous Sessions', path: '/sessions', icon: FileText },
  { label: 'Reports', path: '/report', icon: BarChart3 },
  { label: 'Profile', path: '/profile', icon: UserRound },
  { label: 'Settings', path: '/dashboard', icon: Settings },
]

function Sidebar() {
  const location = useLocation()

  return (
    <aside className="hidden h-screen w-72 flex-col justify-between border-r border-slate-200/80 bg-slate-950/95 p-6 text-slate-100 lg:flex">
      <div>
        <div className="mb-10 flex items-center gap-3">
          <div className="rounded-2xl bg-blue-600 p-2 shadow-lg shadow-blue-600/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-medium text-slate-400">Workplace AI</p>
            <h2 className="text-lg font-semibold">NegotiateAI</h2>
          </div>
        </div>

        <nav className="space-y-2">
          {items.map((item) => {
            const Icon = item.icon
            const active = location.pathname === item.path

            return (
              <Link
                key={item.label}
                to={item.path}
                className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition ${
                  active ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
      </div>

      <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-4">
        <p className="text-sm text-slate-400">Today’s focus</p>
        <p className="mt-2 text-lg font-semibold text-white">Close a $145k offer</p>
        <p className="mt-2 text-sm text-slate-400">Use the recruiter simulator to refine your tone and stance.</p>
      </div>
    </aside>
  )
}

export default Sidebar
