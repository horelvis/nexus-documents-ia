// Team related types for API responses

export interface TeamInfo {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  members_count: number
  storage_quota: number
  is_active: boolean
}

export interface TeamMember {
  id: string
  email: string
  full_name: string | null
  is_team_member: boolean
  is_active: boolean
  created_at: string
  role: string
  subscription_plan: string
  invited_at: string | null
}

export interface TeamInvitation {
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

// Request types
export interface InviteMemberData {
  email: string
  role: string
}

export interface UpdateTeamData {
  name: string
  description: string
}

export interface CreateInvitationData {
  expires_in_days: number
}

// Response types
export interface TeamResponse {
  data: TeamInfo
  error?: string
  status: number
}

export interface TeamMembersResponse {
  data: TeamMember[]
  error?: string
  status: number
}

export interface TeamInvitationsResponse {
  data: TeamInvitation[]
  error?: string
  status: number
}

export interface InvitationResponse {
  data: TeamInvitation
  error?: string
  status: number
}

export interface DeleteMemberResponse {
  data: { message: string }
  error?: string
  status: number
}