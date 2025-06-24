'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
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
  Copy
} from 'lucide-react'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import Image from 'next/image'

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
  
  // Dialog states
  const [showEditTeam, setShowEditTeam] = useState(false)
  const [showInviteDialog, setShowInviteDialog] = useState(false)
  const [showQRDialog, setShowQRDialog] = useState(false)
  const [selectedInvitation, setSelectedInvitation] = useState<TeamInvitation | null>(null)
  
  // Form data
  const [editTeamData, setEditTeamData] = useState<UpdateTeamData>({ name: '', description: '' })
  const [inviteData, setInviteData] = useState<InviteMemberData>({ email: '', role: 'member' })
  const [invitationExpiry, setInvitationExpiry] = useState(7)

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
        setEditTeamData({
          name: teamResponse.data.name,
          description: teamResponse.data.description || ''
        })
      }

      // Load team members
      const membersResponse = await apiClient.get<TeamMember[]>('/teams/members')
      if (!membersResponse.error && membersResponse.data) {
        setMembers(membersResponse.data)
      }

      // Load invitations
      const invitationsResponse = await apiClient.get<TeamInvitation[]>('/teams/invitations')
      if (!invitationsResponse.error && invitationsResponse.data) {
        setInvitations(invitationsResponse.data)
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

  const handleUpdateTeam = async () => {
    try {
      const response = await apiClient.put<TeamInfo>('/teams/', editTeamData)
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

  const handleInviteMember = async () => {
    try {
      const response = await apiClient.post<{ message: string }>('/teams/members/invite', inviteData)
      if (!response.error) {
        setShowInviteDialog(false)
        setInviteData({ email: '', role: 'member' })
        toast({
          title: 'Success',
          description: `Invitation sent to ${inviteData.email}`
        })
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
          <Button onClick={() => setShowEditTeam(true)} size="sm" variant="outline">
            <Settings className="w-4 h-4 mr-2" />
            Edit Team
          </Button>
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
      <div className="flex flex-col sm:flex-row gap-4">
        <Button onClick={() => setShowInviteDialog(true)}>
          <Mail className="w-4 h-4 mr-2" />
          Invite by Email
        </Button>
        <Button onClick={handleCreateInvitationLink} variant="outline">
          <QrCode className="w-4 h-4 mr-2" />
          Generate QR Code
        </Button>
      </div>

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
                        <DropdownMenuItem 
                          onClick={() => handleRemoveMember(member.id)}
                          className="text-destructive"
                          disabled={member.role === 'Admin'}
                        >
                          <Trash className="w-4 h-4 mr-2" />
                          Remove Member
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Edit Team Dialog */}
      <Dialog open={showEditTeam} onOpenChange={setShowEditTeam}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Team Information</DialogTitle>
            <DialogDescription>
              Update your team name and description
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Team Name</Label>
              <Input
                value={editTeamData.name}
                onChange={(e) => setEditTeamData({ ...editTeamData, name: e.target.value })}
                placeholder="Enter team name"
              />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea
                value={editTeamData.description}
                onChange={(e) => setEditTeamData({ ...editTeamData, description: e.target.value })}
                placeholder="Enter team description"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditTeam(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdateTeam}>
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Invite Member Dialog */}
      <Dialog open={showInviteDialog} onOpenChange={setShowInviteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invite Team Member</DialogTitle>
            <DialogDescription>
              Send an email invitation to join your team
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Email Address</Label>
              <Input
                type="email"
                value={inviteData.email}
                onChange={(e) => setInviteData({ ...inviteData, email: e.target.value })}
                placeholder="member@example.com"
              />
            </div>
            <div>
              <Label>Role</Label>
              <Select
                value={inviteData.role}
                onValueChange={(value) => setInviteData({ ...inviteData, role: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="member">Team Member</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowInviteDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleInviteMember}>
              Send Invitation
            </Button>
          </DialogFooter>
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
                <Image 
                  src={selectedInvitation.qr_code} 
                  alt="QR Code" 
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