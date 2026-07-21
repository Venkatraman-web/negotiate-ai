import { useState } from 'react'
import { ArrowRight, CheckCircle2, SendHorizonal, Sparkles } from 'lucide-react'
import './App.css'

const scenarios = [
  { id: 'salary', title: 'Salary Negotiation', subtitle: 'Discuss your worth with confidence' },
  { id: 'freelance', title: 'Freelance Project', subtitle: 'Win a stronger rate and scope' },
]

const personalities = [
  { id: 'friendly', name: 'Friendly', emoji: '😊', description: 'Warm and encouraging' },
  { id: 'aggressive', name: 'Aggressive', emoji: '😠', description: 'Direct and forceful' },
  { id: 'logical', name: 'Logical', emoji: '🧠', description: 'Calm and analytical' },
  { id: 'cooperative', name: 'Cooperative', emoji: '🤝', description: 'Balanced and collaborative' },
  { id: 'manipulative', name: 'Manipulative', emoji: '🦈', description: 'Strategic and sharp' },
]

const initialMessages = [
  { id: 1, role: 'ai', text: 'Welcome. I am your negotiation partner. Let us begin with your opening position.' },
  { id: 2, role: 'ai', text: 'You can make your case clearly, but remember to stay calm and grounded.' },
  { id: 3, role: 'user', text: 'I would like to discuss a stronger package for this role.' },
  { id: 4, role: 'ai', text: 'That is a solid start. Now show me how you would defend your request.' },
]

function App() {
  const [screen, setScreen] = useState('landing')
  const [selectedScenario, setSelectedScenario] = useState('salary')
  const [selectedPersonality, setSelectedPersonality] = useState('friendly')
  const [messages, setMessages] = useState(initialMessages)
  const [draft, setDraft] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [round, setRound] = useState(1)
  const [currentOffer, setCurrentOffer] = useState('12')
  const [trustLevel, setTrustLevel] = useState(50)
  const [patienceLevel, setPatienceLevel] = useState(100)
  const [report, setReport] = useState(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const currentScenario = scenarios.find((item) => item.id === selectedScenario)
  const currentPersonality = personalities.find((item) => item.id === selectedPersonality)

  const startNegotiation = async () => {
    setIsLoading(true)
    setStatusMessage('')

    try {
      const response = await fetch('http://127.0.0.1:8001/start-negotiation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: currentScenario?.title ?? 'Salary Negotiation',
          personality: currentPersonality?.name ?? 'Aggressive',
        }),
      })

      if (!response.ok) {
        throw new Error('Unable to start the negotiation session.')
      }

      const data = await response.json()
      setSessionId(data.session_id)
      setRound(data.round)
      setTrustLevel(50)      // matches create_session() defaults in negotiation_engine.py
      setPatienceLevel(100)  // matches create_session() defaults in negotiation_engine.py
      setMessages(initialMessages)
      setDraft('')
      setStatusMessage(data.message)
      setScreen('chat')
    } catch (error) {
      setStatusMessage('Could not reach the backend. Make sure the FastAPI server is running on port 8000.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSend = async () => {
    if (!draft.trim() || !sessionId) return

    const userMessage = { id: Date.now(), role: 'user', text: draft.trim() }
    setMessages((prev) => [...prev, userMessage])
    setDraft('')
    setIsLoading(true)

    try {
      const response = await fetch('http://127.0.0.1:8001/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: userMessage.text }),
      })

      if (!response.ok) {
        throw new Error('Unable to send the message.')
      }

      const data = await response.json()
      const aiReply = {
        id: Date.now() + 1,
        role: 'ai',
        text: data.reply,
      }

      setMessages((prev) => [...prev, aiReply])
      setRound(data.round)
      setCurrentOffer(data.current_offer)
      setTrustLevel(data.trust)
      setPatienceLevel(data.patience)
    } catch (error) {
      const fallbackReply = {
        id: Date.now() + 2,
        role: 'ai',
        text: 'The backend is unavailable right now. Please try again in a moment.',
      }
      setMessages((prev) => [...prev, fallbackReply])
    } finally {
      setIsLoading(false)
    }
  }

  const finishNegotiation = async () => {
    if (!sessionId) return

    setIsLoading(true)
    setStatusMessage('')

    try {
      const response = await fetch('http://127.0.0.1:8001/finish-negotiation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      })

      if (!response.ok) {
        throw new Error('Unable to finish the negotiation.')
      }

      const data = await response.json()
      console.log(data)
      setReport({
        ...data.objective_metrics,
        ...data.ai_evaluation,
      })
      setScreen('report')
    } catch (error) {
      setStatusMessage('The report endpoint could not be reached. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const resetSession = () => {
    setMessages(initialMessages)
    setDraft('')
    setSelectedScenario('salary')
    setSelectedPersonality('friendly')
    setSessionId('')
    setRound(1)
    setCurrentOffer('12 LPA')
    setReport(null)
    setStatusMessage('')
    setScreen('landing')
    setTrustLevel(50)
    setPatienceLevel(100)
  }

  const renderLanding = () => (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10 text-slate-100">
      <div className="w-full max-w-5xl rounded-[32px] border border-slate-800 bg-slate-900/80 p-8 shadow-2xl shadow-black/30 sm:p-10 lg:p-14">
        <div className="max-w-2xl">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800 px-3 py-1 text-sm text-slate-300">
            <Sparkles className="h-4 w-4 text-blue-400" />
            Practice realistic negotiations
          </div>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Negotia AI</h1>
          <p className="mt-4 text-lg leading-8 text-slate-400">
            Practice real-world negotiations with AI and improve your persuasion skills.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <button
              onClick={() => setScreen('scenario')}
              className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-500"
            >
              Start Negotiation <ArrowRight className="h-4 w-4" />
            </button>
            <button
              onClick={() => setScreen('landing')}
              className="rounded-full border border-slate-700 px-5 py-3 font-medium text-slate-300 transition hover:border-blue-500 hover:text-white"
            >
              Learn More
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  const renderScenario = () => (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl rounded-[32px] border border-slate-800 bg-slate-900/80 p-6 shadow-2xl shadow-black/30 sm:p-8 lg:p-10">
        <div className="mb-8">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-blue-400">Step 1</p>
          <h2 className="mt-2 text-3xl font-semibold">Choose a scenario</h2>
          <p className="mt-2 text-slate-400">Pick the kind of conversation you want to practice.</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {scenarios.map((item) => {
            const active = selectedScenario === item.id
            return (
              <button
                key={item.id}
                onClick={() => setSelectedScenario(item.id)}
                className={`rounded-[24px] border p-5 text-left transition ${
                  active
                    ? 'border-blue-500 bg-blue-600/10 shadow-lg shadow-blue-500/10'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold">{item.title}</h3>
                  {active ? <CheckCircle2 className="h-5 w-5 text-blue-400" /> : null}
                </div>
                <p className="mt-2 text-sm text-slate-400">{item.subtitle}</p>
              </button>
            )
          })}
        </div>

        <div className="mt-8 flex justify-end">
          <button
            onClick={() => setScreen('personality')}
            className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-500"
          >
            Next <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )

  const renderPersonality = () => (
    <div className="min-h-screen bg-slate-950 px-4 py-10 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl rounded-[32px] border border-slate-800 bg-slate-900/80 p-6 shadow-2xl shadow-black/30 sm:p-8 lg:p-10">
        <div className="mb-8">
          <p className="text-sm font-semibold uppercase tracking-[0.3em] text-blue-400">Step 2</p>
          <h2 className="mt-2 text-3xl font-semibold">Choose an AI personality</h2>
          <p className="mt-2 text-slate-400">Each personality changes the tone of the negotiation.</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {personalities.map((item) => {
            const active = selectedPersonality === item.id
            return (
              <button
                key={item.id}
                onClick={() => setSelectedPersonality(item.id)}
                className={`rounded-[24px] border p-5 text-left transition ${
                  active
                    ? 'border-blue-500 bg-blue-600/10 shadow-lg shadow-blue-500/10'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                }`}
              >
                <div className="text-3xl">{item.emoji}</div>
                <h3 className="mt-3 text-lg font-semibold">{item.name}</h3>
                <p className="mt-2 text-sm text-slate-400">{item.description}</p>
              </button>
            )
          })}
        </div>

        <div className="mt-8 flex justify-end">
          <button
            onClick={startNegotiation}
            disabled={isLoading}
            className="inline-flex items-center gap-2 rounded-full bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {isLoading ? 'Connecting...' : 'Start Chat'} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        {statusMessage ? <p className="mt-4 text-sm text-slate-400">{statusMessage}</p> : null}
      </div>
    </div>
  )

  const renderChat = () => (
    <div className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[1.7fr_0.8fr]">
        <div className="overflow-hidden rounded-[32px] border border-slate-800 bg-slate-900/80 shadow-2xl shadow-black/20">
          <div className="border-b border-slate-800 px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-400">Negotiation with {currentPersonality?.name}</p>
                <h2 className="text-lg font-semibold">{currentScenario?.title}</h2>
              </div>
              <div className="rounded-full border border-slate-700 px-3 py-1 text-sm text-slate-300">
                Round {round}
              </div>
            </div>
          </div>

          <div className="h-[420px] space-y-3 overflow-y-auto bg-slate-950/50 p-4">
            {messages.map((item) => (
              <div key={item.id} className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                    item.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 text-slate-200'
                  }`}
                >
                  {item.text}
                </div>
              </div>
            ))}
          </div>

          <div className="border-t border-slate-800 p-4">
            <div className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/70 p-3">
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Type your response..."
                className="flex-1 bg-transparent text-sm outline-none"
              />
              <button
                onClick={handleSend}
                disabled={isLoading}
                className="rounded-full bg-blue-600 p-2 text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-70"
              >
                <SendHorizonal className="h-4 w-4" />
              </button>
            </div>
            <button
              onClick={finishNegotiation}
              disabled={isLoading}
              className="mt-3 w-full rounded-full border border-slate-700 px-4 py-3 text-sm font-medium text-slate-300 transition hover:border-blue-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isLoading ? 'Working...' : 'Finish Negotiation'}
            </button>
            {statusMessage ? <p className="mt-3 text-center text-sm text-slate-400">{statusMessage}</p> : null}
          </div>
        </div>

        <div className="rounded-[32px] border border-slate-800 bg-slate-900/80 p-5 shadow-2xl shadow-black/20">
          <h3 className="text-lg font-semibold">Negotiation Status</h3>
          <div className="mt-5 space-y-4 text-sm text-slate-300">
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Scenario</p>
              <p className="mt-1 font-medium text-white">{currentScenario?.title}</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Current Round</p>
              <p className="mt-1 font-medium text-white">{round}</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Negotiation Progress</p>
              <div className="mt-2 h-2 rounded-full bg-slate-800">
                <div className="h-2 w-[68%] rounded-full bg-blue-500" />
              </div>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Current Offer</p>
              <p className="mt-1 font-medium text-white">{currentOffer} LPA</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Target Offer</p>
              <p className="mt-1 font-medium text-white">16 LPA</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Trust Level</p>
              <p className="mt-1 font-medium text-white">{trustLevel}%</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">Patience Level</p>
              <p className="mt-1 font-medium text-white">{patienceLevel}%</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
              <p className="text-slate-400">AI Personality</p>
              <p className="mt-1 font-medium text-white">{currentPersonality?.name}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )

  const renderReport = () => (
    <div className="min-h-screen bg-slate-950 px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl rounded-[32px] border border-slate-800 bg-slate-900/80 p-6 shadow-2xl shadow-black/30 sm:p-8 lg:p-10">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.3em] text-blue-400">Negotiation Report</p>
            <h2 className="mt-2 text-3xl font-semibold">Overall Negotiation Score</h2>
            <p className="mt-2 text-slate-400">{report ? `${report.overall_score} / 100` : '84 / 100'}</p>
          </div>
          <div className="rounded-[24px] border border-blue-500/30 bg-blue-600/10 px-6 py-5 text-center">
            <p className="text-sm text-slate-400">Performance</p>
            <p className="mt-2 text-4xl font-semibold text-blue-400">{report ? report.overall_score : 84}</p>
          </div>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[
  ['Clarity', report?.communication?.clarity ?? '-'],
  ['Professionalism', report?.communication?.professionalism ?? '-'],
  ['Tone', report?.communication?.tone ?? '-'],
  ['Confidence', report?.negotiation_skills?.confidence ?? '-'],
  ['Persuasiveness', report?.negotiation_skills?.persuasiveness ?? '-'],
].map(([title, score]) => (
            <div key={title} className="rounded-[24px] border border-slate-800 bg-slate-950/60 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{title}</h3>
                <span className="text-blue-400">{score}/100</span>
              </div>
              <div className="mt-3 h-2 rounded-full bg-slate-800">
                <div className="h-2 rounded-full bg-blue-500" style={{ width: `${score}%` }} />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <div className="rounded-[24px] border border-slate-800 bg-slate-950/60 p-5">
            <h3 className="text-xl font-semibold">Strengths</h3>
            <ul className="mt-4 space-y-3 text-sm text-slate-300">
              {(report?.strengths ?? ['Good confidence', 'Clear arguments', 'Professional tone']).map((item, index) => (
                <li
                key={index}
                className="rounded-xl border border-slate-700 p-3"
            >
                <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-green-400" />
                    <span className="font-medium">{item}</span>
                </div>
            
            </li>
              ))}
            </ul>
          </div>
          <div className="rounded-[24px] border border-slate-800 bg-slate-950/60 p-5">
            <h3 className="text-xl font-semibold">Weaknesses</h3>
            <ul className="mt-4 space-y-3 text-sm text-slate-300">
              {(report?.weaknesses ?? ['Accepted the first counteroffer', 'Could ask more questions', 'Missed leverage points']).map((item, index) => (
                <li
                key={index}
                className="rounded-xl border border-slate-700 p-3"
            >
                <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-red-400" />
                    <span className="font-medium">{item}</span>
                </div>
            
            </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <div className="rounded-[24px] border border-slate-800 bg-slate-950/60 p-5">
            <h3 className="text-xl font-semibold">Suggested Better Responses</h3>
            <div className="mt-4 space-y-3">
    {(report?.personalized_suggestions ?? []).map((item, index) => (
        <div
            key={index}
            className="rounded-2xl border border-slate-800 bg-slate-900 p-3"
        >
            {item}
        </div>
    ))}
</div>
          </div>
        </div>

        <div className="mt-8 rounded-[24px] border border-slate-800 bg-slate-950/60 p-5">
    <h3 className="text-xl font-semibold">
        Overall Summary
    </h3>

    <p className="mt-3 text-slate-300 leading-7">
        {report?.overall_summary}
    </p>
</div>

        <div className="mt-8 flex flex-wrap gap-3">
          <button
            onClick={() => setScreen('chat')}
            className="rounded-full border border-slate-700 px-5 py-3 font-medium text-slate-300 transition hover:border-blue-500 hover:text-white"
          >
            Back to Chat
          </button>
          <button
            onClick={resetSession}
            className="rounded-full bg-blue-600 px-5 py-3 font-medium text-white transition hover:bg-blue-500"
          >
            Start New Negotiation
          </button>
        </div>
      </div>
    </div>
  )

  if (screen === 'landing') return renderLanding()
  if (screen === 'scenario') return renderScenario()
  if (screen === 'personality') return renderPersonality()
  if (screen === 'chat') return renderChat()
  return renderReport()
}

export default App
