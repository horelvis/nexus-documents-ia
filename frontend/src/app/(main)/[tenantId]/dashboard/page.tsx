import { DataTable } from "@/components/common/data-table"
import { SectionCards } from "@/components/dashboard/section-cards"
import { StripeDebug } from "@/components/debug/stripe-debug"

import data from "./data.json"

export default function Page() {
  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <SectionCards />
      {/* Temporary debug component */}
      {process.env.NODE_ENV === 'development' && (
        <StripeDebug />
      )}
      <DataTable data={data} />
    </div>
  )
}
