"use client"

import React from 'react'
import { useUser } from '@clerk/nextjs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { UserDeletionDialog } from "@/components/lgpd/user-deletion-dialog"
import { Shield, User, Mail, Calendar, AlertTriangle, Crown } from 'lucide-react'

export default function UserSettingsPage() {
  const { user, isLoaded } = useUser()

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground">Usuário não encontrado</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Configurações da Conta</h1>
        <p className="text-muted-foreground">
          Gerencie suas informações pessoais e configurações de privacidade
        </p>
      </div>

      {/* User Profile Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Informações Pessoais
          </CardTitle>
          <CardDescription>
            Suas informações básicas de perfil
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Nome Completo</label>
              <div className="flex items-center gap-2">
                <span className="text-sm">{user.fullName || 'Não informado'}</span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Email Principal</label>
              <div className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{user.primaryEmailAddress?.emailAddress}</span>
                {user.primaryEmailAddress?.verification?.status === 'verified' && (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    Verificado
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Conta Criada</label>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">
                  {user.createdAt ? new Date(user.createdAt).toLocaleDateString('pt-BR') : 'Não informado'}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Último Acesso</label>
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">
                  {user.lastSignInAt ? new Date(user.lastSignInAt).toLocaleString('pt-BR') : 'Nunca'}
                </span>
              </div>
            </div>
          </div>

          {/* Additional User Info */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Emails Adicionais</label>
            <div className="space-y-1">
              {user.emailAddresses?.slice(1).map((email, index) => (
                <div key={index} className="flex items-center gap-2 text-sm">
                  <Mail className="h-3 w-3 text-muted-foreground" />
                  <span>{email.emailAddress}</span>
                  {email.verification?.status === 'verified' ? (
                    <Badge variant="outline" className="text-xs">Verificado</Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs">Não verificado</Badge>
                  )}
                </div>
              )) || (
                <span className="text-sm text-muted-foreground">Nenhum email adicional</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Account Security */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Segurança da Conta
          </CardTitle>
          <CardDescription>
            Configurações de segurança e autenticação
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Autenticação de Dois Fatores</label>
              <div className="flex items-center gap-2">
                {user.twoFactorEnabled ? (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    Ativado
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    Inativo
                  </Badge>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-muted-foreground">Status da Conta</label>
              <div className="flex items-center gap-2">
                {user.banned ? (
                  <Badge variant="destructive" className="text-xs">Banido</Badge>
                ) : (
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="h-3 w-3 mr-1" />
                    Ativo
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <Alert>
            <Shield className="h-4 w-4" />
            <AlertTitle>Gerenciar Segurança</AlertTitle>
            <AlertDescription>
              Para alterar sua senha, configurar 2FA ou outras configurações de segurança, 
              acesse o <strong>painel de usuário do Clerk</strong> através do menu do seu perfil.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      <Separator />

      {/* LGPD Section */}
      <Card className="border-red-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Proteção de Dados (LGPD)
          </CardTitle>
          <CardDescription>
            Seus direitos conforme a Lei Geral de Proteção de Dados
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-4">
            <div>
              <h4 className="font-medium mb-2">Seus Direitos Sob a LGPD</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-muted-foreground">
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div>
                      <strong>Acesso aos dados:</strong> Você pode solicitar informações sobre quais dados pessoais possuímos
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div>
                      <strong>Correção de dados:</strong> Você pode solicitar a correção de dados incorretos ou desatualizados
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-yellow-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div>
                      <strong>Portabilidade:</strong> Você pode solicitar seus dados em formato legível por máquina
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-2 h-2 bg-red-500 rounded-full mt-2 flex-shrink-0"></div>
                    <div>
                      <strong>Exclusão de dados:</strong> Você pode solicitar a remoção completa de seus dados pessoais
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Zona de Perigo</AlertTitle>
              <AlertDescription className="space-y-2">
                <p>
                  A exclusão da conta remove <strong>permanentemente</strong> todos os seus dados pessoais 
                  do sistema, incluindo documentos, histórico de atividades e configurações.
                </p>
                <p className="font-medium">Esta ação é irreversível e não pode ser desfeita.</p>
              </AlertDescription>
            </Alert>

            <div className="flex justify-between items-center pt-4">
              <div>
                <p className="text-sm font-medium">Exclusão Completa de Dados</p>
                <p className="text-sm text-muted-foreground">
                  Remove permanentemente todos os seus dados pessoais conforme LGPD Art. 18
                </p>
              </div>
              <UserDeletionDialog />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Legal Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Crown className="h-5 w-5" />
            Informações Legais
          </CardTitle>
          <CardDescription>
            Base legal para o tratamento dos seus dados
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="text-sm text-muted-foreground space-y-2">
            <p>
              <strong>Lei aplicável:</strong> Lei Geral de Proteção de Dados (LGPD) - Lei nº 13.709/2018
            </p>
            <p>
              <strong>Base legal:</strong> Execução de contrato (Art. 7º, V) e consentimento (Art. 7º, I)
            </p>
            <p>
              <strong>Finalidade:</strong> Prestação de serviços de gestão documental e processamento de IA
            </p>
            <p>
              <strong>Retenção:</strong> Dados mantidos enquanto a conta estiver ativa ou por período legal necessário
            </p>
            <p>
              <strong>Controlador:</strong> NexusDocs360 - Contato: privacy@nexusdocs360.com
            </p>
          </div>

          <Alert>
            <Shield className="h-4 w-4" />
            <AlertDescription>
              Para exercer seus direitos sob a LGPD ou esclarecer dúvidas sobre o tratamento 
              de seus dados pessoais, entre em contato através do email: <strong>privacy@nexusdocs360.com</strong>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    </div>
  )
}