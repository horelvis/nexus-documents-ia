"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  Calculator,
  Calendar,
  CreditCard,
  Settings,
  Smile,
  User,
  FileText,
  LayoutDashboard,
  Search,
  Plus,
  LogOut,
  Bot
} from "lucide-react"

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command"

interface GlobalCommandMenuProps {
  tenantId: string
}

export function GlobalCommandMenu({ tenantId }: GlobalCommandMenuProps) {
  const [open, setOpen] = React.useState(false)
  const router = useRouter()

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }

    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  const runCommand = React.useCallback((command: () => void) => {
    setOpen(false)
    command()
  }, [])

  return (
    <CommandDialog 
      open={open} 
      onOpenChange={setOpen}
      className="top-auto bottom-8 translate-y-0"
    >
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Suggestions">
          <CommandItem
            onSelect={() => runCommand(() => router.push(`/${tenantId}/dashboard`))}
          >
            <LayoutDashboard className="mr-2 h-4 w-4" />
            <span>Dashboard</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push(`/${tenantId}/documents`))}
          >
            <FileText className="mr-2 h-4 w-4" />
            <span>Documents</span>
          </CommandItem>
          <CommandItem
            onSelect={() => runCommand(() => router.push(`/${tenantId}/agents`))}
          >
            <Bot className="mr-2 h-4 w-4" />
            <span>Agents (Emma)</span>
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem
            onSelect={() => {
                // Trigger upload dialog if possible, otherwise nav to upload
                runCommand(() => router.push(`/${tenantId}/documents?action=upload`))
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            <span>New Document</span>
            <CommandShortcut>⌘N</CommandShortcut>
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Settings">
          <CommandItem
            onSelect={() => runCommand(() => router.push(`/${tenantId}/settings`))}
          >
            <Settings className="mr-2 h-4 w-4" />
            <span>Settings</span>
            <CommandShortcut>⌘S</CommandShortcut>
          </CommandItem>
           <CommandItem
            onSelect={() => runCommand(() => router.push(`/${tenantId}/settings/profile`))}
          >
            <User className="mr-2 h-4 w-4" />
            <span>Profile</span>
            <CommandShortcut>⌘P</CommandShortcut>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
