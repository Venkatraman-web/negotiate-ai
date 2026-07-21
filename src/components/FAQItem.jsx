import { ChevronDown } from 'lucide-react'

function FAQItem({ question, answer, open, onToggle }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="font-medium text-slate-900 dark:text-slate-100">{question}</span>
        <ChevronDown className={`h-5 w-5 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open ? <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400">{answer}</p> : null}
    </div>
  )
}

export default FAQItem
