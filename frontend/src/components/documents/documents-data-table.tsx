"use client"

import * as React from "react"
import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import {
  IconEye,
  IconDownload,
  IconEdit,
  IconTrash,
  IconPhoto,
  IconDotsVertical,
  IconArrowUp,
  IconArrowDown,
  IconArrowsUpDown,
  IconChevronLeft,
  IconChevronRight,
  IconChevronsLeft,
  IconChevronsRight,
  IconShare2,
  IconSignature,
  IconRefresh,
  IconFileTypeDoc,
  IconLoader2,
  IconMessageCircle,
  IconFolderFilled,
} from "@tabler/icons-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Document as ApiDocument } from "@/lib/types"
import { getFileIcon, formatFileSize } from "@/lib/document-utils"

// Extended type to support both documents and folders
type TableItem = ApiDocument & {
  type?: 'document' | 'folder'
  folder_path?: string
  document_count?: number
}

interface DocumentsDataTableProps {
  data: TableItem[]
  onViewDocument: (document: ApiDocument) => void
  onEditDocument: (document: ApiDocument) => void
  onDeleteDocument: (document: ApiDocument) => void
  onDownloadDocument: (document: ApiDocument) => void
  onPreviewDocument: (document: ApiDocument) => void
  onFullPagePreview: (document: ApiDocument) => void
  onShareDocument: (document: ApiDocument) => void
  onFolderClick?: (folderPath: string) => void  // Google Drive style folder navigation
  onRequestSignature?: (document: ApiDocument) => void
  onConvertToTemplate?: (document: ApiDocument) => void
  onAskEmma?: (document: ApiDocument) => void
  canConvertToTemplate?: boolean
  convertLoadingId?: string | null
}

export function DocumentsDataTable({
  data,
  onViewDocument,
  onEditDocument,
  onDeleteDocument,
  onDownloadDocument,
  onPreviewDocument,
  onFullPagePreview,
  onShareDocument,
  onFolderClick,
  onRequestSignature,
  onConvertToTemplate,
  onAskEmma,
  canConvertToTemplate,
  convertLoadingId,
}: DocumentsDataTableProps) {
  // Helper functions for localStorage
  const getStoredPreference = (key: string, defaultValue: any) => {
    if (typeof window === 'undefined') return defaultValue
    try {
      const stored = localStorage.getItem(`documents_table_${key}`)
      return stored ? JSON.parse(stored) : defaultValue
    } catch {
      return defaultValue
    }
  }

  const storePreference = (key: string, value: any) => {
    if (typeof window === 'undefined') return
    try {
      localStorage.setItem(`documents_table_${key}`, JSON.stringify(value))
    } catch {
      // Ignore localStorage errors
    }
  }

  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>(() =>
    getStoredPreference('columnVisibility', {})
  )
  const [rowSelection, setRowSelection] = React.useState({})
  const [pagination, setPagination] = React.useState(() => ({
    pageIndex: 0,
    pageSize: getStoredPreference('pageSize', 10),
  }))

  const columns: ColumnDef<ApiDocument>[] = [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected() ||
            (table.getIsSomePageRowsSelected() && "indeterminate")
          }
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      id: "icon",
      header: () => null,
      cell: ({ row }) => {
        const item = row.original as TableItem
        // Render folder icon for folders
        if (item.type === 'folder') {
          return (
            <div className="flex items-center justify-center">
              <IconFolderFilled className="h-5 w-5 text-muted-foreground" />
            </div>
          )
        }
        return (
          <div className="flex items-center justify-center">
            {getFileIcon(item.file_type, item.mime_type, item.filename)}
          </div>
        )
      },
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: "filename",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="h-auto p-0 font-medium"
          >
            Name
            {column.getIsSorted() === "asc" ? (
              <IconArrowUp className="ml-2 h-4 w-4" />
            ) : column.getIsSorted() === "desc" ? (
              <IconArrowDown className="ml-2 h-4 w-4" />
            ) : (
              <IconArrowsUpDown className="ml-2 h-4 w-4" />
            )}
          </Button>
        )
      },
      cell: ({ row }) => {
        const item = row.original as TableItem

        // Folder rendering
        if (item.type === 'folder') {
          return (
            <div>
              <div
                className="font-medium cursor-pointer hover:text-primary hover:underline transition-colors"
                onClick={(e) => {
                  e.stopPropagation()
                  if (onFolderClick && item.folder_path) {
                    onFolderClick(item.folder_path)
                  }
                }}
              >
                {item.title || item.folder_path?.split('/').pop() || 'Carpeta'}
              </div>
              <div className="text-xs text-muted-foreground">
                {item.document_count || 0} {item.document_count === 1 ? 'documento' : 'documentos'}
              </div>
            </div>
          )
        }

        // Document rendering
        return (
          <div>
            <div
              className="font-medium cursor-pointer hover:text-primary hover:underline transition-colors"
              onClick={(e) => {
                e.stopPropagation()
                onFullPagePreview(item)
              }}
            >
              {item.title || item.filename}
            </div>
            {item.description && (
              <div className="text-xs text-muted-foreground line-clamp-1">
                {item.description}
              </div>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: "file_size",
      header: "Size",
      cell: ({ row }) => {
        const item = row.original as TableItem
        // Don't show size for folders
        if (item.type === 'folder') {
          return <span className="text-sm text-muted-foreground">—</span>
        }
        return <span className="text-sm">{formatFileSize(item.file_size)}</span>
      },
    },
    {
      accessorKey: "created_at",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="h-auto p-0 font-medium"
          >
            Uploaded
            {column.getIsSorted() === "asc" ? (
              <IconArrowUp className="ml-2 h-4 w-4" />
            ) : column.getIsSorted() === "desc" ? (
              <IconArrowDown className="ml-2 h-4 w-4" />
            ) : (
              <IconArrowsUpDown className="ml-2 h-4 w-4" />
            )}
          </Button>
        )
      },
      cell: ({ row }) => {
        const item = row.original as TableItem
        // Don't show date for folders
        if (item.type === 'folder') {
          return <span className="text-sm text-muted-foreground">—</span>
        }
        return (
          <span className="text-sm">
            {new Date(item.created_at).toLocaleDateString()}
          </span>
        )
      },
    },
    {
      accessorKey: "category",
      header: "Category",
      cell: ({ row }) => {
        const item = row.original as TableItem
        if (item.type === 'folder') {
          return <span className="text-muted-foreground">—</span>
        }
        return item.category || "Sin Categoría"
      },
    },
    {
      accessorKey: "tags",
      header: "Tags",
      cell: ({ row }) => {
        const item = row.original as TableItem
        // Don't show tags for folders
        if (item.type === 'folder') {
          return <span className="text-muted-foreground">—</span>
        }
        const tags = item.tags || []
        if (tags.length === 0) return "-"

        return (
          <div className="flex flex-wrap gap-0.5">
            {tags.slice(0, 2).map((tag: string) => (
              <Badge key={tag} variant="outline" className="text-xs px-1.5 py-0 h-5">
                {tag}
              </Badge>
            ))}
            {tags.length > 2 && (
              <Badge variant="outline" className="text-xs px-1.5 py-0 h-5">
                +{tags.length - 2}
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      id: "actions",
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const item = row.original as TableItem

        // For folders, show minimal actions or navigate on click
        if (item.type === 'folder') {
          return (
            <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={() => {
                  if (onFolderClick && item.folder_path) {
                    onFolderClick(item.folder_path)
                  }
                }}
                title="Abrir carpeta"
              >
                <IconEye className="h-4 w-4" />
                <span className="sr-only">Abrir carpeta</span>
              </Button>
            </div>
          )
        }

        // Document actions
        return (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {/* 3 Main Actions */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onFullPagePreview(item)}
              title="Full Preview"
            >
              <IconEye className="h-4 w-4" />
              <span className="sr-only">Full Preview</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onDownloadDocument(item)}
              title="Download"
            >
              <IconDownload className="h-4 w-4" />
              <span className="sr-only">Download</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onShareDocument(item)}
              title="Share"
            >
              <IconShare2 className="h-4 w-4" />
              <span className="sr-only">Share</span>
            </Button>

            {/* More Actions Dropdown */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                >
                  <IconDotsVertical className="h-4 w-4" />
                  <span className="sr-only">More actions</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onClick={() => onViewDocument(item)}>
                  <IconEye className="mr-2 h-4 w-4" />
                  View Details
                </DropdownMenuItem>
                {onAskEmma && (
                  <DropdownMenuItem onClick={() => onAskEmma(item)}>
                    <IconMessageCircle className="mr-2 h-4 w-4" />
                    Ask Emma
                  </DropdownMenuItem>
                )}
                {onRequestSignature && (
                  <DropdownMenuItem onClick={() => onRequestSignature(item)}>
                    <IconSignature className="mr-2 h-4 w-4" />
                    Request Signature
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={() => onEditDocument(item)}>
                  <IconEdit className="mr-2 h-4 w-4" />
                  Edit
                </DropdownMenuItem>
                {canConvertToTemplate && onConvertToTemplate && (
                  <DropdownMenuItem
                    onClick={() => onConvertToTemplate(item)}
                    disabled={convertLoadingId === item.id}
                  >
                    {convertLoadingId === item.id ? (
                      <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <IconFileTypeDoc className="mr-2 h-4 w-4" />
                    )}
                    Convert to Template
                  </DropdownMenuItem>
                )}


                <DropdownMenuSeparator />

                <DropdownMenuItem
                  onClick={() => onDeleteDocument(item)}
                  className="text-red-600 focus:text-red-600"
                >
                  <IconTrash className="mr-2 h-4 w-4" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )
      },
    },
  ]

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: (updater) => {
      const newVisibility = typeof updater === 'function' 
        ? updater(columnVisibility)
        : updater
      setColumnVisibility(newVisibility)
      storePreference('columnVisibility', newVisibility)
    },
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      pagination,
    },
  })

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => {
                const item = row.original as TableItem
                const isFolder = item.type === 'folder'

                return (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => {
                    if (isFolder && onFolderClick && item.folder_path) {
                      onFolderClick(item.folder_path)
                    } else if (!isFolder) {
                      onViewDocument(item)
                    }
                  }}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
                )
              })
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      
      {/* Table Pagination */}
      <div className="flex items-center justify-between px-2">
        <div className="flex-1 text-sm text-muted-foreground">
          {table.getFilteredSelectedRowModel().rows.length} of{" "}
          {table.getFilteredRowModel().rows.length} row(s) selected.
        </div>
        <div className="flex items-center space-x-6 lg:space-x-8">
          <div className="flex items-center space-x-2">
            <p className="text-sm font-medium">Rows per page</p>
            <Select
              value={`${table.getState().pagination.pageSize}`}
              onValueChange={(value) => {
                const pageSize = Number(value)
                table.setPageSize(pageSize)
                storePreference('pageSize', pageSize)
              }}
            >
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue placeholder={table.getState().pagination.pageSize} />
              </SelectTrigger>
              <SelectContent side="top">
                {[10, 20, 30, 40, 50].map((pageSize) => (
                  <SelectItem key={pageSize} value={`${pageSize}`}>
                    {pageSize}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex w-[100px] items-center justify-center text-sm font-medium">
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              className="hidden h-8 w-8 p-0 lg:flex"
              onClick={() => table.setPageIndex(0)}
              disabled={!table.getCanPreviousPage()}
            >
              <span className="sr-only">Go to first page</span>
              <IconChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="h-8 w-8 p-0"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <span className="sr-only">Go to previous page</span>
              <IconChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="h-8 w-8 p-0"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <span className="sr-only">Go to next page</span>
              <IconChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              className="hidden h-8 w-8 p-0 lg:flex"
              onClick={() => table.setPageIndex(table.getPageCount() - 1)}
              disabled={!table.getCanNextPage()}
            >
              <span className="sr-only">Go to last page</span>
              <IconChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
