function TestimonialCard({ name, role, quote }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-sm leading-7 text-slate-600 dark:text-slate-300">“{quote}”</p>
      <div className="mt-6">
        <p className="font-semibold text-slate-900 dark:text-slate-100">{name}</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">{role}</p>
      </div>
    </div>
  )
}

export default TestimonialCard
