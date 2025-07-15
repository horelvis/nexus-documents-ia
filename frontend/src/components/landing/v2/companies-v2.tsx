"use client"

import { motion } from "framer-motion"

const companies = [
  "Microsoft", "Google", "Amazon", "Salesforce", "Adobe", "Oracle", "IBM", "SAP"
]

export function CompaniesV2() {
  return (
    <section className="relative px-6 py-16 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <motion.div
          className="text-center mb-12"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
        >
          <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-8">
            Empresas líderes confían en nuestra tecnología
          </p>
          
          <div className="flex flex-wrap items-center justify-center gap-8 opacity-60">
            {companies.map((company, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 * index }}
                viewport={{ once: true }}
                className="text-lg font-semibold text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
              >
                {company}
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}