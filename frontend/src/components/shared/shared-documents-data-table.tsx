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
  IconLink, 
  IconMail, 
  IconUsers,
  IconCalendar,
  IconEye,
  IconEdit,
  IconX,
  IconCopy,
  IconExternalLink,
  IconDotsVertical,
  IconArrowUp,
  IconArrowDown,
  IconArrowsUpDown,
  IconChevronLeft,
  IconChevronRight,
  IconChevronsLeft,
  IconChevronsRight
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
import { SharedDocument } from "@/lib/services/shared-documents.service"
import { formatDistanceToNow } from "date-fns"

interface SharedDocumentsDataTableProps {
  data: SharedDocument[]
  onCopyLink: (share: SharedDocument) => void
  onOpenLink: (share: SharedDocument) => void
  onEditShare: (share: SharedDocument) => void
  onRevokeShare: (share: SharedDocument) => void
}

export function SharedDocumentsDataTable({
  data,
  onCopyLink,
  onOpenLink,
  onEditShare,
  onRevokeShare,
}: SharedDocumentsDataTableProps) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
  const [rowSelection, setRowSelection] = React.useState({})
  const [pagination, setPagination] = React.useState({
    pageIndex: 0,
    pageSize: 10,
  })

  const getShareIcon = (share: SharedDocument) => {
    if (share.recipient_email) {
      return <IconMail className="h-4 w-4" />
    }
    return <IconLink className="h-4 w-4" />
  }

  const getStatusBadge = (share: SharedDocument) => {
    if (!share.is_active) {
      return <Badge variant="secondary" className="text-xs">Revoked</Badge>
    }
    
    if (share.expires_at) {
      const expiresDate = new Date(share.expires_at)
      const now = new Date()
      
      if (expiresDate < now) {
        return <Badge variant="destructive" className="text-xs">Expired</Badge>
      }
      
      const daysUntilExpiry = Math.ceil((expiresDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
      
      if (daysUntilExpiry <= 3) {
        return <Badge variant="secondary" className="text-xs">Expires in {daysUntilExpiry} days</Badge>
      }
    }
    
    return <Badge variant="outline" className="text-xs">Active</Badge>
  }

  const columns: ColumnDef<SharedDocument>[] = [
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
      id: "document",
      accessorFn: (row) => row.document_title || row.document_filename || 'Untitled',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-3 h-8 data-[state=open]:bg-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            Document
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
        const share = row.original
        const documentName = share.document_title || share.document_filename || 'Untitled'
        return (
          <div className="flex items-center gap-2">
            <IconEye className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{documentName}</span>
          </div>
        )
      },
    },
    {
      id: "shared_with",
      header: "Shared With",
      cell: ({ row }) => {
        const share = row.original
        const sharedWith = share.recipient_email || share.recipient_name || 'Public link'
        return (
          <div className="flex items-center gap-2">
            {getShareIcon(share)}
            <span className="text-sm">{sharedWith}</span>
          </div>
        )
      },
    },
    {
      id: "permissions",
      header: "Permissions",
      cell: ({ row }) => {
        const share = row.original
        const perms = share.permissions || {}
        const permArray: string[] = []
        
        // Default share_type determines base permissions
        if (share.share_type === 'view' || perms.view !== false) permArray.push('view')
        if (share.share_type === 'download' || perms.download) permArray.push('download')
        if (share.share_type === 'edit' || perms.edit) permArray.push('edit')
        
        if (permArray.length === 0) permArray.push('view') // Default to view
        
        return (
          <div className="flex flex-wrap gap-1">
            {permArray.map((perm) => (
              <Badge key={perm} variant="secondary" className="text-xs capitalize">
                {perm}
              </Badge>
            ))}
          </div>
        )
      },
    },
    {
      accessorKey: "current_access_count",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-3 h-8 data-[state=open]:bg-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            Views
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
        const share = row.original
        return (
          <div className="text-sm">
            <div>{share.current_access_count} views</div>
            {share.last_accessed_at && (
              <div className="text-xs text-muted-foreground">
                Last {formatDistanceToNow(new Date(share.last_accessed_at), { addSuffix: true })}
              </div>
            )}
            {share.max_access_count && (
              <div className="text-xs text-muted-foreground">
                {share.max_access_count - share.current_access_count} remaining
              </div>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: "expires_at",
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-3 h-8 data-[state=open]:bg-accent"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            Expires
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
        const expiresAt = row.getValue("expires_at") as string | null
        return expiresAt ? (
          <div className="text-sm flex items-center gap-1">
            <IconCalendar className="h-4 w-4" />
            {new Date(expiresAt).toLocaleDateString()}
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">Never</span>
        )
      },
    },
    {
      id: "status",
      header: "Status",
      cell: ({ row }) => {
        return getStatusBadge(row.original)
      },
    },
    {
      id: "actions",
      enableHiding: false,
      cell: ({ row }) => {
        const share = row.original
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <IconDotsVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onCopyLink(share)}>
                <IconCopy className="mr-2 h-4 w-4" />
                Copy Link
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onOpenLink(share)}>
                <IconExternalLink className="mr-2 h-4 w-4" />
                Open Link
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => onEditShare(share)}>
                <IconEdit className="mr-2 h-4 w-4" />
                Edit Permissions
              </DropdownMenuItem>
              {share.is_active && (
                <DropdownMenuItem 
                  onClick={() => onRevokeShare(share)}
                  className="text-red-600"
                >
                  <IconX className="mr-2 h-4 w-4" />
                  Revoke Access
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
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
    onColumnVisibilityChange: setColumnVisibility,
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
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
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
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  <div className="flex flex-col items-center justify-center py-8">
                    <p className="text-lg font-medium mb-2">No shared documents found</p>
                    <p className="text-sm text-muted-foreground">Go to the Document Library to share your first document.</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      
      {/* Pagination */}
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
                table.setPageSize(Number(value))
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