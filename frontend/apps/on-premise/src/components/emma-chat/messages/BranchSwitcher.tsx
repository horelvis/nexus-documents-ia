'use client'

import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface BranchSwitcherProps {
  branch?: string
  branchOptions?: string[]
  onSelect: (branch: string) => void
  isLoading?: boolean
}

export function BranchSwitcher({ branch, branchOptions, onSelect, isLoading }: BranchSwitcherProps) {
  if (!branchOptions || branchOptions.length <= 1) return null
  const currentIndex = branch != null ? branchOptions.indexOf(branch) : -1
  if (currentIndex < 0) return null

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        disabled={isLoading || currentIndex === 0}
        onClick={() => onSelect(branchOptions[currentIndex - 1])}
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </Button>
      <span className="text-xs text-muted-foreground">
        {currentIndex + 1}/{branchOptions.length}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        disabled={isLoading || currentIndex === branchOptions.length - 1}
        onClick={() => onSelect(branchOptions[currentIndex + 1])}
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
