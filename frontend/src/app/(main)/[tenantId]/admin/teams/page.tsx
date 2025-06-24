'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import { 
  Users, 
  Search, 
  MoreVertical, 
  Mail, 
  Check,
  X,
  Trash,
  Settings,
  QrCode,
  Clock,
  Copy,
  Loader2,
  Send
} from 'lucide-react'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import { useApiClient } from '@/lib/api-client'
import type {
  TeamInfo,
  TeamMember,
  TeamInvitation,
  InviteMemberData,
  UpdateTeamData} from '@/lib/types/teams'

// Form validation schemas
const inviteMemberSchema = z.object({
  email: z.string().email('Invalid email address'),
  role: z.enum(['member', 'admin'], {
    required_error: 'Please select a role',
  }),
})

const updateTeamSchema = z.object({
  name: z.string().min(1, 'Team name is required').max(100, 'Team name is too long'),
  description: z.string().max(500, 'Description is too long').optional(),
})

type InviteMemberFormData = z.infer<typeof inviteMemberSchema>
type UpdateTeamFormData = z.infer<typeof updateTeamSchema>

export default function TeamsPage() {
  const params = useParams()
  const { user } = useUser()
  const { toast } = useToast()
  const apiClient = useApiClient()

  const [isLoading, setIsLoading] = useState(true)
  const [teamInfo, setTeamInfo] = useState<TeamInfo | null>(null)
  const [members, setMembers] = useState<TeamMember[]>([])
  const [invitations, setInvitations] = useState<TeamInvitation[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  
  // Dialog states
  const [showEditTeam, setShowEditTeam] = useState(false)
  const [showInviteDialog, setShowInviteDialog] = useState(false)
  const [showQRDialog, setShowQRDialog] = useState(false)
  const [selectedInvitation, setSelectedInvitation] = useState<TeamInvitation | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null)
  const [deletingItemType, setDeletingItemType] = useState<'member' | 'invitation' | null>(null)
  
  // Form data
  const [invitationExpiry, setInvitationExpiry] = useState(7)
  
  // React Hook Form for invite member
  const inviteForm = useForm<InviteMemberFormData>({
    resolver: zodResolver(inviteMemberSchema),
    defaultValues: {
      email: '',
      role: 'member',
    },
  })
  
  // React Hook Form for update team
  const updateTeamForm = useForm<UpdateTeamFormData>({
    resolver: zodResolver(updateTeamSchema),
    defaultValues: {
      name: '',
      description: '',
    },
  })
  
  // Loading states
  const [isGeneratingQR, setIsGeneratingQR] = useState(false)
  const [revokingInvitationId, setRevokingInvitationId] = useState<string | null>(null)
  const [resendingInvitationId, setResendingInvitationId] = useState<string | null>(null)

  // Load team info and members
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setIsLoading(true)
    try {
      // Load team info
      const teamResponse = await apiClient.get<TeamInfo>('/teams/')
      if (!teamResponse.error && teamResponse.data) {
        setTeamInfo(teamResponse.data)
        updateTeamForm.reset({
          name: teamResponse.data.name,
          description: teamResponse.data.description || ''
        })
      }

      // Load team members
      const membersResponse = await apiClient.get<TeamMember[]>('/teams/members')
      if (!membersResponse.error && membersResponse.data) {
        setMembers(membersResponse.data)
        
        // Check if current user is admin
        const currentMember = membersResponse.data.find(m => m.email === user?.emailAddresses?.[0]?.emailAddress)
        setIsAdmin(currentMember?.role === 'Admin' || !currentMember?.is_team_member)
      }

      // Load invitations (only for admins)
      const invitationsResponse = await apiClient.get<TeamInvitation[]>('/teams/invitations')
      if (!invitationsResponse.error && invitationsResponse.data) {
        setInvitations(invitationsResponse.data)
      } else if (invitationsResponse.error) {
        // Silently ignore 403 errors for non-admins
        if (!invitationsResponse.error.includes('403')) {
          console.error('Error loading invitations:', invitationsResponse.error)
        }
      }
    } catch (error) {
      console.error('Error loading data:', error)
      toast({
        title: 'Error',
        description: 'Failed to load team data',
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleUpdateTeam = async (data: UpdateTeamFormData) => {
    try {
      const response = await apiClient.put<TeamInfo>('/teams/', data)
      if (!response.error && response.data) {
        setTeamInfo(response.data)
        setShowEditTeam(false)
        toast({
          title: 'Success',
          description: 'Team information updated successfully'
        })
      } else {
        throw new Error(response.error || 'Failed to update team')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to update team information',
        variant: 'destructive'
      })
    }
  }

  const handleInviteMember = async (data: InviteMemberFormData) => {
    try {
      const response = await apiClient.post<{ 
        message: string
        email_sent: boolean
        invitation_link?: string 
      }>('/teams/members/invite', data)
      
      if (!response.error && response.data) {
        setShowInviteDialog(false)
        inviteForm.reset()
        
        if (response.data.email_sent) {
          toast({
            title: 'Success',
            description: `Invitation sent to ${data.email}`
          })
        } else if (response.data.invitation_link) {
          // Show invitation link if email failed
          toast({
            title: 'Invitation Created',
            description: (
              <div className="space-y-2">
                <p>Email service is unavailable. Share this link with {data.email}:</p>
                <code className="block text-xs bg-muted p-2 rounded">
                  {response.data.invitation_link}
                </code>
              </div>
            ) as any,
            duration: 10000 // Show for 10 seconds
          })
        }
        
        loadData() // Reload to update members list
      } else {
        throw new Error(response.error || 'Failed to send invitation')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to send invitation',
        variant: 'destructive'
      })
    }
  }

  const handleCreateInvitationLink = async () => {
    setIsGeneratingQR(true)
    try {
      const response = await apiClient.post<TeamInvitation>('/teams/invitations', {
        expires_in_days: invitationExpiry
      })
      if (!response.error && response.data) {
        setSelectedInvitation(response.data)
        setShowQRDialog(true)
        loadData() // Reload invitations
      } else {
        throw new Error(response.error || 'Failed to create invitation')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to create invitation link',
        variant: 'destructive'
      })
    } finally {
      setIsGeneratingQR(false)
    }
  }

  const handleRemoveMember = async (memberId: string) => {
    if (!confirm('Are you sure you want to remove this member?')) return

    try {
      const response = await apiClient.delete<{ message: string }>(`/teams/members/${memberId}`)
      if (!response.error) {
        toast({
          title: 'Success',
          description: 'Member removed successfully'
        })
        loadData()
      } else {
        throw new Error(response.error || 'Failed to remove member')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to remove member',
        variant: 'destructive'
      })
    }
  }

  const handleRevokeInvitation = async (invitationId: string) => {
    if (!confirm('Are you sure you want to revoke this invitation?')) return

    setRevokingInvitationId(invitationId)
    try {
      const response = await apiClient.delete<{ message: string }>(`/teams/invitations/${invitationId}`)
      if (!response.error) {
        toast({
          title: 'Success',
          description: 'Invitation revoked successfully'
        })
        loadData()
      } else {
        throw new Error(response.error || 'Failed to revoke invitation')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to revoke invitation',
        variant: 'destructive'
      })
    } finally {
      setRevokingInvitationId(null)
    }
  }

  const handleResendInvitation = async (invitationId: string) => {
    setResendingInvitationId(invitationId)
    try {
      const response = await apiClient.post<{
        message: string
        email_sent: boolean
        invitation_url?: string
      }>(`/teams/invitations/${invitationId}/resend`, {})
      
      if (!response.error && response.data) {
        if (response.data.email_sent) {
          toast({
            title: 'Success',
            description: response.data.message
          })
        } else if (response.data.invitation_url) {
          // Show invitation link if email failed
          toast({
            title: 'Email Service Unavailable',
            description: (
              <div className="space-y-2">
                <p>Email service is unavailable. Copy and share this link:</p>
                <code className="block text-xs bg-muted p-2 rounded">
                  {response.data.invitation_url}
                </code>
              </div>
            ) as any,
            duration: 10000 // Show for 10 seconds
          })
        }
        loadData() // Reload to refresh data
      } else {
        throw new Error(response.error || 'Failed to resend invitation')
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to resend invitation',
        variant: 'destructive'
      })
    } finally {
      setResendingInvitationId(null)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied',
      description: 'Link copied to clipboard'
    })
  }

  const getRoleBadge = (role: string) => {
    if (role === 'Admin') {
      return <Badge variant="default">Admin</Badge>
    }
    return <Badge variant="secondary">Member</Badge>
  }

  const getStatusBadge = (isActive: boolean) => {
    return isActive ? (
      <Badge variant="outline" className="text-green-600">
        <Check className="w-3 h-3 mr-1" />
        Active
      </Badge>
    ) : (
      <Badge variant="outline" className="text-gray-500">
        <X className="w-3 h-3 mr-1" />
        Inactive
      </Badge>
    )
  }

  const filteredMembers = members.filter(member => 
    member.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (member.full_name && member.full_name.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      {/* Team Info Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-2xl font-bold flex items-center gap-2">
              <Users className="w-6 h-6" />
              {teamInfo?.name || 'Team'}
            </CardTitle>
            <CardDescription>
              {teamInfo?.description || 'Manage your team members and settings'}
            </CardDescription>
          </div>
          {isAdmin && (
            <Button onClick={() => setShowEditTeam(true)} size="sm" variant="outline">
              <Settings className="w-4 h-4 mr-2" />
              Edit Team
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Members</p>
              <p className="text-2xl font-bold">{teamInfo?.members_count || 0}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Storage Quota</p>
              <p className="text-2xl font-bold">{teamInfo?.storage_quota || 0} GB</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Created</p>
              <p className="text-sm">
                {teamInfo && format(new Date(teamInfo.created_at), 'PP', { locale: es })}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              {teamInfo && getStatusBadge(teamInfo.is_active)}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      {isAdmin && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <Button onClick={() => setShowInviteDialog(true)}>
              <Mail className="w-4 h-4 mr-2" />
              Invite by Email
            </Button>
            <Button 
              onClick={handleCreateInvitationLink} 
              variant="outline"
              disabled={isGeneratingQR}
            >
              {isGeneratingQR ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <QrCode className="w-4 h-4 mr-2" />
                  Generate QR Code
                </>
              )}
            </Button>
          </div>
          
          {/* Invitation Summary */}
          {invitations.length > 0 && (
            <div className="flex gap-4 text-sm text-muted-foreground">
              <span>
                Active invitations: {invitations.filter(inv => !inv.used && new Date(inv.expires_at) > new Date()).length}
              </span>
              <span>•</span>
              <span>
                Used: {invitations.filter(inv => inv.used).length}
              </span>
              <span>•</span>
              <span>
                Expired: {invitations.filter(inv => !inv.used && new Date(inv.expires_at) <= new Date()).length}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Members Table */}
      <Card>
        <CardHeader>
          <CardTitle>Team Members</CardTitle>
          <CardDescription>
            Manage your team members and their roles
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search members..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Joined</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredMembers.map((member) => (
                <TableRow key={member.id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar>
                        <AvatarFallback>
                          {member.full_name ? member.full_name.charAt(0).toUpperCase() : member.email.charAt(0).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="font-medium">{member.full_name || member.email}</p>
                        <p className="text-sm text-muted-foreground">{member.email}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{getRoleBadge(member.role)}</TableCell>
                  <TableCell>{getStatusBadge(member.is_active)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {format(new Date(member.created_at), 'PP', { locale: es })}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" className="h-8 w-8 p-0">
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Actions</DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        {isAdmin && (
                          <DropdownMenuItem 
                            onClick={() => handleRemoveMember(member.id)}
                            className="text-destructive"
                            disabled={member.role === 'Admin'}
                          >
                            <Trash className="w-4 h-4 mr-2" />
                            Remove Member
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Invitations Table */}
      {isAdmin && invitations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Pending Invitations</CardTitle>
            <CardDescription>
              Active invitation links for your team
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invitations.map((invitation) => (
                  <TableRow key={invitation.id}>
                    <TableCell>
                      {invitation.email || 'Open invitation'}
                    </TableCell>
                    <TableCell>
                      {invitation.used ? (
                        <Badge variant="secondary">Used</Badge>
                      ) : new Date(invitation.expires_at) < new Date() ? (
                        <Badge variant="destructive">Expired</Badge>
                      ) : (
                        <Badge variant="default">Active</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {format(new Date(invitation.expires_at), 'PP', { locale: es })}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {format(new Date(invitation.created_at), 'PP', { locale: es })}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setSelectedInvitation(invitation)
                            setShowQRDialog(true)
                          }}
                          disabled={invitation.used || new Date(invitation.expires_at) < new Date()}
                        >
                          <QrCode className="w-4 h-4 mr-2" />
                          View QR
                        </Button>
                        {!invitation.used && new Date(invitation.expires_at) > new Date() && invitation.email && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleResendInvitation(invitation.id)}
                                  disabled={resendingInvitationId === invitation.id}
                                >
                                  {resendingInvitationId === invitation.id ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <Send className="w-4 h-4" />
                                  )}
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Resend invitation email</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                        {!invitation.used && new Date(invitation.expires_at) > new Date() && (
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => handleRevokeInvitation(invitation.id)}
                                  className="text-destructive hover:text-destructive"
                                  disabled={revokingInvitationId === invitation.id}
                                >
                                  {revokingInvitationId === invitation.id ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <X className="w-4 h-4" />
                                  )}
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Revoke invitation</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Edit Team Dialog */}
      <Dialog 
        open={showEditTeam} 
        onOpenChange={(open) => {
          if (!updateTeamForm.formState.isSubmitting) {
            setShowEditTeam(open)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Team Information</DialogTitle>
            <DialogDescription>
              Update your team name and description
            </DialogDescription>
          </DialogHeader>
          <Form {...updateTeamForm}>
            <form onSubmit={updateTeamForm.handleSubmit(handleUpdateTeam)} className="space-y-4">
              <FormField
                control={updateTeamForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Team Name</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Enter team name"
                        {...field}
                        disabled={updateTeamForm.formState.isSubmitting}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={updateTeamForm.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Enter team description"
                        rows={3}
                        {...field}
                        disabled={updateTeamForm.formState.isSubmitting}
                      />
                    </FormControl>
                    <FormDescription>
                      A brief description of your team
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button 
                  type="button"
                  variant="outline" 
                  onClick={() => setShowEditTeam(false)}
                  disabled={updateTeamForm.formState.isSubmitting}
                >
                  Cancel
                </Button>
                <Button 
                  type="submit"
                  disabled={updateTeamForm.formState.isSubmitting}
                >
                  {updateTeamForm.formState.isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    'Save Changes'
                  )}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Invite Member Dialog */}
      <Dialog 
        open={showInviteDialog} 
        onOpenChange={(open) => {
          if (!inviteForm.formState.isSubmitting) {
            setShowInviteDialog(open)
            if (!open) {
              inviteForm.reset()
            }
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite Team Member</DialogTitle>
            <DialogDescription>
              Send an email invitation to join your team
            </DialogDescription>
          </DialogHeader>
          <Form {...inviteForm}>
            <form onSubmit={inviteForm.handleSubmit(handleInviteMember)} className="space-y-4">
              <FormField
                control={inviteForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email Address</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        placeholder="member@example.com"
                        {...field}
                        disabled={inviteForm.formState.isSubmitting}
                      />
                    </FormControl>
                    <FormDescription>
                      The email address of the person you want to invite
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={inviteForm.control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      defaultValue={field.value}
                      disabled={inviteForm.formState.isSubmitting}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a role" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="member">Team Member</SelectItem>
                        <SelectItem value="admin">Admin</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Choose the role for this team member
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button 
                  type="button"
                  variant="outline" 
                  onClick={() => setShowInviteDialog(false)}
                  disabled={inviteForm.formState.isSubmitting}
                >
                  Cancel
                </Button>
                <Button 
                  type="submit"
                  disabled={inviteForm.formState.isSubmitting}
                >
                  {inviteForm.formState.isSubmitting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    'Send Invitation'
                  )}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* QR Code Dialog */}
      <Dialog open={showQRDialog} onOpenChange={setShowQRDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Team Invitation QR Code</DialogTitle>
            <DialogDescription>
              Share this QR code or link to invite team members
            </DialogDescription>
          </DialogHeader>
          {selectedInvitation && (
            <div className="space-y-4">
              <div className="flex justify-center">
                <img 
                  src={selectedInvitation.qr_code} 
                  alt="QR Code"
                  width={256}
                  height={256}  
                  className="w-64 h-64"
                />
              </div>
              <div className="space-y-2">
                <Label>Invitation Link</Label>
                <div className="flex gap-2">
                  <Input 
                    value={selectedInvitation.invitation_url} 
                    readOnly 
                    className="flex-1"
                  />
                  <Button
                    size="icon"
                    variant="outline"
                    onClick={() => copyToClipboard(selectedInvitation.invitation_url)}
                  >
                    <Copy className="w-4 h-4" />
                  </Button>
                </div>
              </div>
              <div className="text-sm text-muted-foreground">
                <Clock className="w-4 h-4 inline mr-1" />
                Expires on {format(new Date(selectedInvitation.expires_at), 'PPP', { locale: es })}
              </div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setShowQRDialog(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}