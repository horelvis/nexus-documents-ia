'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { 
  Users, 
  UserPlus, 
  Search, 
  MoreVertical, 
  Shield, 
  Mail, 
  Calendar,
  Check,
  X,
  Edit,
  Trash,
  Key,
  Activity,
  Plus,
  Settings,
  UserCheck,
  QrCode,
  Link,
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
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
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

interface Team {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members_count: number
  created_by: string
}

interface TeamMember {
  user: {
    id: string
    email: string
    name: string | null
    avatar?: string
  }
  role: 'leader' | 'member'
  joined_at: string
}

interface TeamWithMembers extends Team {
  members: TeamMember[]
}

interface CreateTeamData {
  name: string
  description?: string
}

interface UpdateTeamData {
  name?: string
  description?: string
}

interface TeamInvitation {
  id: string
  invitation_code: string
  invitation_url: string
  qr_code: string
  email: string | null
  expires_at: string
  created_at: string
  tenant_name: string
  used: boolean
  used_at: string | null
}

export default function TeamManagementPage() {
  const params = useParams()
  const tenantId = params.tenantId as string
  const { user: currentUser } = useUser()
  const apiClient = useApiClient()
  const { toast } = useToast()

  const [teams, setTeams] = useState<Team[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedTeam, setSelectedTeam] = useState<TeamWithMembers | null>(null)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showMembersDialog, setShowMembersDialog] = useState(false)
  const [showAddMemberDialog, setShowAddMemberDialog] = useState(false)
  const [createData, setCreateData] = useState<CreateTeamData>({ name: '' })
  const [updateData, setUpdateData] = useState<UpdateTeamData>({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [availableUsers, setAvailableUsers] = useState<any[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string>('')
  const [memberRole, setMemberRole] = useState<'leader' | 'member'>('member')
  const [showInvitationsDialog, setShowInvitationsDialog] = useState(false)
  const [showCreateInvitationDialog, setShowCreateInvitationDialog] = useState(false)
  const [invitations, setInvitations] = useState<TeamInvitation[]>([])
  const [invitationEmail, setInvitationEmail] = useState('')
  const [invitationDays, setInvitationDays] = useState(7)
  const [isLoadingInvitations, setIsLoadingInvitations] = useState(false)

  useEffect(() => {
    loadTeams()
  }, [tenantId])

  const loadTeams = async () => {
    try {
      setIsLoading(true)
      const response = await apiClient.get(`/teams`)
      if (response.data) {
        setTeams(response.data.teams)
      }
    } catch (error) {
      console.error('Error loading teams:', error)
      toast({
        title: "Error",
        description: "No se pudieron cargar los equipos",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const loadTeamDetails = async (teamId: string) => {
    try {
      const response = await apiClient.get(`/teams/${teamId}`)
      if (response.data) {
        setSelectedTeam(response.data)
      }
    } catch (error) {
      console.error('Error loading team details:', error)
      toast({
        title: "Error",
        description: "No se pudieron cargar los detalles del equipo",
        variant: "destructive"
      })
    }
  }

  const loadAvailableUsers = async () => {
    try {
      const response = await apiClient.get(`/users/list`)
      if (response.data) {
        setAvailableUsers(response.data)
      }
    } catch (error) {
      console.error('Error loading users:', error)
      toast({
        title: "Error",
        description: "No se pudieron cargar los usuarios disponibles",
        variant: "destructive"
      })
    }
  }

  const handleCreateTeam = async () => {
    try {
      setIsSubmitting(true)
      await apiClient.post('/teams', createData)
      toast({
        title: "Éxito",
        description: "Equipo creado correctamente",
      })
      setShowCreateDialog(false)
      setCreateData({ name: '' })
      loadTeams()
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo crear el equipo",
        variant: "destructive"
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleUpdateTeam = async () => {
    if (!selectedTeam) return
    
    try {
      setIsSubmitting(true)
      await apiClient.put(`/teams/${selectedTeam.id}`, updateData)
      toast({
        title: "Éxito",
        description: "Equipo actualizado correctamente",
      })
      setShowEditDialog(false)
      setUpdateData({})
      loadTeams()
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo actualizar el equipo",
        variant: "destructive"
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteTeam = async () => {
    if (!selectedTeam) return
    
    try {
      setIsSubmitting(true)
      await apiClient.delete(`/teams/${selectedTeam.id}`)
      toast({
        title: "Éxito",
        description: "Equipo eliminado correctamente",
      })
      setShowDeleteDialog(false)
      setSelectedTeam(null)
      loadTeams()
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo eliminar el equipo",
        variant: "destructive"
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAddMember = async () => {
    if (!selectedTeam || !selectedUserId) return
    
    try {
      setIsSubmitting(true)
      await apiClient.post(`/teams/${selectedTeam.id}/members`, {
        user_id: selectedUserId,
        role: memberRole
      })
      toast({
        title: "Éxito",
        description: "Miembro añadido al equipo",
      })
      setShowAddMemberDialog(false)
      setSelectedUserId('')
      setMemberRole('member')
      loadTeamDetails(selectedTeam.id)
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo añadir el miembro al equipo",
        variant: "destructive"
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleUpdateMemberRole = async (userId: string, newRole: 'leader' | 'member') => {
    if (!selectedTeam) return
    
    try {
      await apiClient.put(`/teams/${selectedTeam.id}/members/${userId}/role`, {
        role: newRole
      })
      toast({
        title: "Éxito",
        description: "Rol actualizado correctamente",
      })
      loadTeamDetails(selectedTeam.id)
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo actualizar el rol",
        variant: "destructive"
      })
    }
  }

  const handleRemoveMember = async (userId: string) => {
    if (!selectedTeam) return
    
    try {
      await apiClient.delete(`/teams/${selectedTeam.id}/members/${userId}`)
      toast({
        title: "Éxito",
        description: "Miembro eliminado del equipo",
      })
      loadTeamDetails(selectedTeam.id)
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo eliminar el miembro del equipo",
        variant: "destructive"
      })
    }
  }

  const filteredTeams = teams.filter(team => 
    team.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    team.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getRoleBadge = (role: string) => {
    const roleConfig = {
      leader: { label: 'Líder', variant: 'default' as const },
      member: { label: 'Miembro', variant: 'secondary' as const }
    }
    const config = roleConfig[role as keyof typeof roleConfig] || { label: role, variant: 'outline' as const }
    return <Badge variant={config.variant}>{config.label}</Badge>
  }

  const getInitials = (name: string | null, email: string) => {
    if (name) {
      return name.split(' ').map(n => n[0]).join('').toUpperCase()
    }
    return email.substring(0, 2).toUpperCase()
  }

  const getAvailableUsersForTeam = () => {
    if (!selectedTeam) return availableUsers
    const memberIds = selectedTeam.members.map(m => m.user.id)
    return availableUsers.filter(user => !memberIds.includes(user.id))
  }

  const loadInvitations = async () => {
    try {
      setIsLoadingInvitations(true)
      const response = await apiClient.get(`/teams/invitations`)
      if (response.data) {
        setInvitations(response.data)
      }
    } catch (error) {
      console.error('Error loading invitations:', error)
      toast({
        title: "Error",
        description: "No se pudieron cargar las invitaciones",
        variant: "destructive"
      })
    } finally {
      setIsLoadingInvitations(false)
    }
  }

  const handleCreateInvitation = async () => {
    try {
      setIsSubmitting(true)
      const response = await apiClient.post('/teams/invitations', {
        email: invitationEmail || null,
        expires_in_days: invitationDays
      })
      
      if (response.data) {
        toast({
          title: "Éxito",
          description: "Invitación creada correctamente",
        })
        setShowCreateInvitationDialog(false)
        setInvitationEmail('')
        setInvitationDays(7)
        loadInvitations()
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo crear la invitación",
        variant: "destructive"
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast({
        title: "Copiado",
        description: "El enlace se copió al portapapeles",
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "No se pudo copiar el enlace",
        variant: "destructive"
      })
    }
  }

  return (
    <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
      <div className="px-4 lg:px-6">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Gestión de Equipos</h1>
          <p className="text-muted-foreground">
            Organiza a los usuarios en equipos para una mejor colaboración
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Equipos</CardTitle>
              <Users className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{teams.length}</div>
              <p className="text-xs text-muted-foreground">
                Equipos activos
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Total Miembros</CardTitle>
              <UserCheck className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {teams.reduce((acc, team) => acc + team.members_count, 0)}
              </div>
              <p className="text-xs text-muted-foreground">
                En todos los equipos
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Promedio</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {teams.length > 0 
                  ? Math.round(teams.reduce((acc, team) => acc + team.members_count, 0) / teams.length)
                  : 0
                }
              </div>
              <p className="text-xs text-muted-foreground">
                Miembros por equipo
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Actions Bar */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
            <Input
              placeholder="Buscar equipos por nombre o descripción..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => {
              loadInvitations()
              setShowInvitationsDialog(true)
            }}>
              <QrCode className="h-4 w-4 mr-2" />
              Invitaciones
            </Button>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Crear Equipo
            </Button>
          </div>
        </div>

        {/* Teams Table */}
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-8">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-center space-x-4 mb-4">
                    <Skeleton className="h-12 w-12 rounded-full" />
                    <div className="space-y-2 flex-1">
                      <Skeleton className="h-4 w-[250px]" />
                      <Skeleton className="h-4 w-[200px]" />
                    </div>
                  </div>
                ))}
              </div>
            ) : filteredTeams.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-muted-foreground">
                  {searchQuery ? 'No se encontraron equipos' : 'No hay equipos creados'}
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Equipo</TableHead>
                    <TableHead>Miembros</TableHead>
                    <TableHead>Creado</TableHead>
                    <TableHead>Actualizado</TableHead>
                    <TableHead className="text-right">Acciones</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredTeams.map((team) => (
                    <TableRow key={team.id}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{team.name}</div>
                          {team.description && (
                            <div className="text-sm text-muted-foreground">{team.description}</div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center space-x-1">
                          <Users className="h-4 w-4 text-muted-foreground" />
                          <span>{team.members_count}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">
                          {format(new Date(team.created_at), 'dd MMM yyyy', { locale: es })}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">
                          {format(new Date(team.updated_at), 'dd MMM yyyy', { locale: es })}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Acciones</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={async () => {
                              await loadTeamDetails(team.id)
                              setShowMembersDialog(true)
                            }}>
                              <Users className="h-4 w-4 mr-2" />
                              Ver Miembros
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => {
                              setSelectedTeam(team as TeamWithMembers)
                              setUpdateData({ name: team.name, description: team.description || '' })
                              setShowEditDialog(true)
                            }}>
                              <Edit className="h-4 w-4 mr-2" />
                              Editar
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem 
                              onClick={() => {
                                setSelectedTeam(team as TeamWithMembers)
                                setShowDeleteDialog(true)
                              }}
                              className="text-red-600"
                            >
                              <Trash className="h-4 w-4 mr-2" />
                              Eliminar
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Create Team Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Crear Equipo</DialogTitle>
            <DialogDescription>
              Crea un nuevo equipo para organizar a los usuarios
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Nombre</Label>
              <Input
                id="name"
                placeholder="Equipo de Desarrollo"
                value={createData.name}
                onChange={(e) => setCreateData({ ...createData, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">Descripción (opcional)</Label>
              <Textarea
                id="description"
                placeholder="Equipo responsable del desarrollo de nuevas funcionalidades"
                value={createData.description || ''}
                onChange={(e) => setCreateData({ ...createData, description: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreateTeam} disabled={isSubmitting || !createData.name}>
              {isSubmitting ? 'Creando...' : 'Crear Equipo'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Team Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Equipo</DialogTitle>
            <DialogDescription>
              Actualiza los datos del equipo
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-name">Nombre</Label>
              <Input
                id="edit-name"
                value={updateData.name || ''}
                onChange={(e) => setUpdateData({ ...updateData, name: e.target.value })}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="edit-description">Descripción</Label>
              <Textarea
                id="edit-description"
                value={updateData.description || ''}
                onChange={(e) => setUpdateData({ ...updateData, description: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleUpdateTeam} disabled={isSubmitting}>
              {isSubmitting ? 'Actualizando...' : 'Actualizar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar Equipo</DialogTitle>
            <DialogDescription>
              ¿Estás seguro de que deseas eliminar el equipo {selectedTeam?.name}? 
              Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancelar
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleDeleteTeam}
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Eliminando...' : 'Eliminar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Team Members Dialog */}
      <Dialog open={showMembersDialog} onOpenChange={setShowMembersDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Miembros del Equipo: {selectedTeam?.name}</DialogTitle>
            <DialogDescription>
              Gestiona los miembros de este equipo
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="flex justify-end mb-4">
              <Button 
                size="sm" 
                onClick={() => {
                  loadAvailableUsers()
                  setShowAddMemberDialog(true)
                }}
              >
                <UserPlus className="h-4 w-4 mr-2" />
                Añadir Miembro
              </Button>
            </div>
            {selectedTeam?.members.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No hay miembros en este equipo
              </div>
            ) : (
              <div className="space-y-2">
                {selectedTeam?.members.map((member) => (
                  <div key={member.user.id} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center space-x-3">
                      <Avatar>
                        <AvatarImage src={member.user.avatar} />
                        <AvatarFallback>
                          {getInitials(member.user.name, member.user.email)}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <div className="font-medium">{member.user.name || 'Sin nombre'}</div>
                        <div className="text-sm text-muted-foreground">{member.user.email}</div>
                        <div className="text-xs text-muted-foreground">
                          Desde {format(new Date(member.joined_at), 'dd MMM yyyy', { locale: es })}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      {getRoleBadge(member.role)}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Acciones</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => {
                            handleUpdateMemberRole(
                              member.user.id, 
                              member.role === 'leader' ? 'member' : 'leader'
                            )
                          }}>
                            <Shield className="h-4 w-4 mr-2" />
                            {member.role === 'leader' ? 'Hacer Miembro' : 'Hacer Líder'}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem 
                            onClick={() => handleRemoveMember(member.user.id)}
                            className="text-red-600"
                          >
                            <Trash className="h-4 w-4 mr-2" />
                            Eliminar del Equipo
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Member Dialog */}
      <Dialog open={showAddMemberDialog} onOpenChange={setShowAddMemberDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Añadir Miembro al Equipo</DialogTitle>
            <DialogDescription>
              Selecciona un usuario para añadir al equipo
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="user">Usuario</Label>
              <Select
                value={selectedUserId}
                onValueChange={setSelectedUserId}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecciona un usuario" />
                </SelectTrigger>
                <SelectContent>
                  {getAvailableUsersForTeam().map((user) => (
                    <SelectItem key={user.id} value={user.id}>
                      {user.name || user.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="role">Rol</Label>
              <Select
                value={memberRole}
                onValueChange={(value) => setMemberRole(value as 'leader' | 'member')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="leader">Líder</SelectItem>
                  <SelectItem value="member">Miembro</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddMemberDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleAddMember} disabled={isSubmitting || !selectedUserId}>
              {isSubmitting ? 'Añadiendo...' : 'Añadir al Equipo'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Team Invitations Dialog */}
      <Dialog open={showInvitationsDialog} onOpenChange={setShowInvitationsDialog}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Invitaciones al Equipo</DialogTitle>
            <DialogDescription>
              Gestiona las invitaciones para unirse a tu organización
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="flex justify-end mb-4">
              <Button onClick={() => setShowCreateInvitationDialog(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Crear Invitación
              </Button>
            </div>
            {isLoadingInvitations ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-32 w-full" />
                ))}
              </div>
            ) : invitations.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No hay invitaciones creadas
              </div>
            ) : (
              <div className="space-y-4">
                {invitations.map((invitation) => (
                  <Card key={invitation.id}>
                    <CardContent className="p-6">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* QR Code */}
                        <div className="flex justify-center md:justify-start">
                          <img 
                            src={invitation.qr_code} 
                            alt="QR Code"
                            className="w-32 h-32"
                          />
                        </div>
                        
                        {/* Invitation Details */}
                        <div className="col-span-2 space-y-4">
                          <div>
                            <h4 className="font-medium mb-2">Detalles de la Invitación</h4>
                            <div className="space-y-2 text-sm">
                              {invitation.email && (
                                <div className="flex items-center gap-2">
                                  <Mail className="h-4 w-4 text-muted-foreground" />
                                  <span>Restringido a: {invitation.email}</span>
                                </div>
                              )}
                              <div className="flex items-center gap-2">
                                <Clock className="h-4 w-4 text-muted-foreground" />
                                <span>
                                  Expira: {format(new Date(invitation.expires_at), 'dd MMM yyyy HH:mm', { locale: es })}
                                </span>
                              </div>
                              <div className="flex items-center gap-2">
                                <Calendar className="h-4 w-4 text-muted-foreground" />
                                <span>
                                  Creada: {format(new Date(invitation.created_at), 'dd MMM yyyy', { locale: es })}
                                </span>
                              </div>
                              {invitation.used && (
                                <div className="flex items-center gap-2">
                                  <Check className="h-4 w-4 text-green-600" />
                                  <span className="text-green-600">
                                    Usada el {format(new Date(invitation.used_at!), 'dd MMM yyyy', { locale: es })}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                          
                          <div>
                            <h4 className="font-medium mb-2">Enlace de Invitación</h4>
                            <div className="flex items-center gap-2">
                              <Input 
                                value={invitation.invitation_url} 
                                readOnly 
                                className="flex-1"
                              />
                              <Button
                                size="icon"
                                variant="outline"
                                onClick={() => copyToClipboard(invitation.invitation_url)}
                              >
                                <Copy className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <Badge variant={invitation.used ? "secondary" : "default"}>
                              {invitation.used ? "Usada" : "Activa"}
                            </Badge>
                            {new Date(invitation.expires_at) < new Date() && !invitation.used && (
                              <Badge variant="destructive">Expirada</Badge>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Create Invitation Dialog */}
      <Dialog open={showCreateInvitationDialog} onOpenChange={setShowCreateInvitationDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Crear Invitación</DialogTitle>
            <DialogDescription>
              Genera un enlace con código QR para invitar usuarios a tu organización
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="invitation-email">Email (opcional)</Label>
              <Input
                id="invitation-email"
                type="email"
                placeholder="usuario@ejemplo.com"
                value={invitationEmail}
                onChange={(e) => setInvitationEmail(e.target.value)}
              />
              <p className="text-sm text-muted-foreground">
                Si especificas un email, solo ese usuario podrá usar la invitación
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="invitation-days">Días de validez</Label>
              <Select
                value={invitationDays.toString()}
                onValueChange={(value) => setInvitationDays(parseInt(value))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 día</SelectItem>
                  <SelectItem value="3">3 días</SelectItem>
                  <SelectItem value="7">7 días</SelectItem>
                  <SelectItem value="14">14 días</SelectItem>
                  <SelectItem value="30">30 días</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateInvitationDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleCreateInvitation} disabled={isSubmitting}>
              {isSubmitting ? 'Creando...' : 'Crear Invitación'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}