'use client'

import * as React from 'react'
import { Check, ChevronsUpDown, FileText, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from './button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from './popover'
import { Badge } from './badge'
import { Skeleton } from './skeleton'

interface Document {
  id: string
  filename: string
  mime_type: string
  file_size: number
  created_at: string
}

interface DocumentSearchComboboxProps {
  value?: string
  onValueChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  documents: Document[]
  isLoading?: boolean
  onSearch?: (search: string) => void
}

export function DocumentSearchCombobox({
  value,
  onValueChange,
  placeholder = 'Select a document...',
  disabled = false,
  documents = [],
  isLoading = false,
  onSearch,
}: DocumentSearchComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [searchTerm, setSearchTerm] = React.useState('')

  // Find selected document
  const selectedDocument = documents.find((doc) => doc.id === value)

  // Filter documents based on search
  const filteredDocuments = React.useMemo(() => {
    if (!searchTerm) return documents
    
    const search = searchTerm.toLowerCase()
    return documents.filter((doc) => 
      doc.filename.toLowerCase().includes(search)
    )
  }, [documents, searchTerm])

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // Format date
  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(date)
  }

  const handleSearchChange = (search: string) => {
    setSearchTerm(search)
    if (onSearch) {
      onSearch(search)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
          disabled={disabled}
        >
          {selectedDocument ? (
            <div className="flex items-center gap-2 truncate">
              <FileText className="h-4 w-4 flex-shrink-0" />
              <span className="truncate">{selectedDocument.filename}</span>
            </div>
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[500px] p-0" align="start">
        <Command shouldFilter={false}>
          <div className="flex items-center border-b px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <input
              className="flex h-10 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Search documents..."
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>
          <CommandList>
            {isLoading ? (
              <div className="p-4 space-y-2">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : filteredDocuments.length === 0 ? (
              <CommandEmpty>
                <div className="py-6 text-center text-sm">
                  {searchTerm ? `No documents found matching "${searchTerm}"` : 'No documents found'}
                </div>
              </CommandEmpty>
            ) : (
              <CommandGroup>
                {filteredDocuments.map((doc) => (
                  <CommandItem
                    key={doc.id}
                    value={doc.id}
                    onSelect={(currentValue) => {
                      onValueChange(currentValue === value ? '' : currentValue)
                      setOpen(false)
                    }}
                    className="flex items-start gap-3 p-2"
                  >
                    <Check
                      className={cn(
                        'mt-1 h-4 w-4',
                        value === doc.id ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                    <FileText className="mt-1 h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium truncate">{doc.filename}</span>
                        {doc.mime_type === 'application/pdf' && (
                          <Badge variant="secondary" className="text-xs">PDF</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <span>{formatFileSize(doc.file_size)}</span>
                        <span>•</span>
                        <span>{formatDate(doc.created_at)}</span>
                      </div>
                    </div>
                  </CommandItem>
                ))}
                {documents.length > filteredDocuments.length && (
                  <div className="py-2 px-3 text-xs text-muted-foreground text-center">
                    Showing {filteredDocuments.length} of {documents.length} documents
                  </div>
                )}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}