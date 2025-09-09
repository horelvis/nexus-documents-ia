"use client"

import React, { useState } from 'react'
import { AlertTriangle, Trash2, Shield, FileText, Eye } from 'lucide-react'
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Separator } from "@/components/ui/separator"
import { useUser } from '@clerk/nextjs'

interface UserDataSummary {
  user_id: string
  email: string
  full_name: string | null
  tenant: string
  created_at: string
  data_summary: {
    profile_data: {
      user_record: number
      user_image: number
      external_accounts: {
        clerk: boolean
        stripe: boolean
      }
    }
    document_data: {
      documents_created: number
      document_views: number
    }
    access_data: {
      role_assignments: number
    }
    audit_data: {
      note: string
      retention_reason: string
    }
  }
  lgpd_rights: {
    article_18: string
    deletion_scope: string
    audit_retention: string
    external_services: string
  }
}

interface DeletionResult {
  user_id: string
  deletion_id: string
  status: string
  deleted_at: string
  summary: {
    deleted_records: Record<string, number>
    anonymized_records: number
    storage_deletions: Record<string, any>
    external_deletions: Record<string, any>
    errors: string[]
  }
  lgpd_compliance: {
    article: string
    method: string
    anonymization_applied: boolean
    external_services_notified: Record<string, any>
  }
}

export function UserDeletionDialog() {
  const { user } = useUser()
  const [isOpen, setIsOpen] = useState(false)
  const [step, setStep] = useState<'info' | 'summary' | 'confirm' | 'processing' | 'completed'>('info')
  const [dataSummary, setDataSummary] = useState<UserDataSummary | null>(null)
  const [deletionResult, setDeletionResult] = useState<DeletionResult | null>(null)
  const [confirmationEmail, setConfirmationEmail] = useState('')
  const [confirmationText, setConfirmationText] = useState('')
  const [reason, setReason] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const REQUIRED_CONFIRMATION = "DELETE MY ACCOUNT PERMANENTLY"

  const fetchDataSummary = async () => {
    try {
      setIsLoading(true)
      setError(null)
      
      const response = await fetch('/api/v1/lgpd/data-summary', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${await user?.getToken()}`,
          'Content-Type': 'application/json'
        }
      })
      
      if (!response.ok) {
        throw new Error('Failed to fetch data summary')
      }
      
      const summary = await response.json()
      setDataSummary(summary)
      setStep('summary')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
    } finally {
      setIsLoading(false)
    }
  }

  const submitDeletionRequest = async () => {
    try {
      setIsLoading(true)
      setError(null)
      setStep('processing')
      
      const response = await fetch('/api/v1/lgpd/request-deletion', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${await user?.getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          confirmation_email: confirmationEmail,
          confirmation_text: confirmationText,
          reason: reason.trim() || null
        })
      })
      
      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Deletion request failed')
      }
      
      const result = await response.json()
      setDeletionResult(result)
      setStep('completed')
      
      // User will be logged out automatically as their account no longer exists
      setTimeout(() => {
        window.location.href = '/'
      }, 10000)
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred')
      setStep('confirm')
    } finally {
      setIsLoading(false)
    }
  }

  const resetDialog = () => {
    setStep('info')
    setDataSummary(null)
    setDeletionResult(null)
    setConfirmationEmail('')
    setConfirmationText('')
    setReason('')
    setError(null)
    setIsLoading(false)
  }

  const canProceedToConfirmation = dataSummary && 
    confirmationEmail === user?.emailAddresses?.[0]?.emailAddress &&
    confirmationText === REQUIRED_CONFIRMATION

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      setIsOpen(open)
      if (!open) resetDialog()
    }}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm" className="gap-2">
          <Trash2 className="h-4 w-4" />
          Excluir Conta (LGPD)
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-5 w-5" />
            Exclusão de Dados - LGPD
          </DialogTitle>
          <DialogDescription>
            Exercício do direito de exclusão de dados pessoais conforme Lei Geral de Proteção de Dados (LGPD)
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Erro</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Step 1: Information */}
        {step === 'info' && (
          <div className="space-y-6">
            <Alert>
              <Shield className="h-4 w-4" />
              <AlertTitle>Seus Direitos Sob a LGPD</AlertTitle>
              <AlertDescription>
                De acordo com o Artigo 18 da LGPD, você tem o direito de solicitar a exclusão completa 
                de seus dados pessoais. Esta ação é <strong>irreversível</strong> e removerá permanentemente 
                todos os seus dados do sistema.
              </AlertDescription>
            </Alert>

            <div className="space-y-4">
              <h4 className="font-medium">O que será excluído:</h4>
              <ul className="space-y-2 text-sm text-muted-foreground ml-4">
                <li>• Perfil de usuário e informações pessoais</li>
                <li>• Todos os documentos criados por você</li>
                <li>• Histórico de visualizações e atividades</li>
                <li>• Dados armazenados em serviços externos (Clerk, Stripe)</li>
                <li>• Arquivos em armazenamento na nuvem</li>
                <li>• Índices de busca e dados vetoriais</li>
              </ul>
            </div>

            <div className="space-y-4">
              <h4 className="font-medium">O que será mantido (anonimizado):</h4>
              <ul className="space-y-2 text-sm text-muted-foreground ml-4">
                <li>• Registros de auditoria (para conformidade legal)</li>
                <li>• Logs de sistema sem identificação pessoal</li>
              </ul>
            </div>

            <div className="flex gap-4">
              <Button 
                onClick={fetchDataSummary}
                disabled={isLoading}
                className="gap-2"
              >
                <Eye className="h-4 w-4" />
                {isLoading ? 'Carregando...' : 'Ver Resumo dos Dados'}
              </Button>
              <Button variant="outline" onClick={() => setIsOpen(false)}>
                Cancelar
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Data Summary */}
        {step === 'summary' && dataSummary && (
          <div className="space-y-6">
            <div>
              <h4 className="font-medium mb-4">Resumo dos Seus Dados</h4>
              
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">Email:</span> {dataSummary.email}
                </div>
                <div>
                  <span className="font-medium">Nome:</span> {dataSummary.full_name || 'Não informado'}
                </div>
                <div>
                  <span className="font-medium">Organização:</span> {dataSummary.tenant}
                </div>
                <div>
                  <span className="font-medium">Conta criada:</span> {new Date(dataSummary.created_at).toLocaleDateString('pt-BR')}
                </div>
              </div>
            </div>

            <Separator />

            <div>
              <h5 className="font-medium mb-2">Dados que serão excluídos:</h5>
              <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
                <div>Documentos criados: <strong>{dataSummary.data_summary.document_data.documents_created}</strong></div>
                <div>Visualizações: <strong>{dataSummary.data_summary.document_data.document_views}</strong></div>
                <div>Funções atribuídas: <strong>{dataSummary.data_summary.access_data.role_assignments}</strong></div>
                <div>Imagem do perfil: <strong>{dataSummary.data_summary.profile_data.user_image ? 'Sim' : 'Não'}</strong></div>
                <div>Conta Clerk: <strong>{dataSummary.data_summary.profile_data.external_accounts.clerk ? 'Sim' : 'Não'}</strong></div>
                <div>Conta Stripe: <strong>{dataSummary.data_summary.profile_data.external_accounts.stripe ? 'Sim' : 'Não'}</strong></div>
              </div>
            </div>

            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Ação Irreversível</AlertTitle>
              <AlertDescription>
                Uma vez confirmada, esta ação não pode ser desfeita. Todos os seus dados serão 
                permanentemente removidos do sistema dentro de 30 dias.
              </AlertDescription>
            </Alert>

            <div className="flex gap-4">
              <Button 
                onClick={() => setStep('confirm')}
                variant="destructive"
                className="gap-2"
              >
                <Trash2 className="h-4 w-4" />
                Prosseguir com Exclusão
              </Button>
              <Button variant="outline" onClick={() => setStep('info')}>
                Voltar
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Confirmation */}
        {step === 'confirm' && (
          <div className="space-y-6">
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Confirmação Final</AlertTitle>
              <AlertDescription>
                Para confirmar a exclusão permanente de sua conta, você deve:
              </AlertDescription>
            </Alert>

            <div className="space-y-4">
              <div>
                <Label htmlFor="confirmation-email">
                  Confirme seu email: <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confirmation-email"
                  type="email"
                  value={confirmationEmail}
                  onChange={(e) => setConfirmationEmail(e.target.value)}
                  placeholder={user?.emailAddresses?.[0]?.emailAddress}
                />
              </div>

              <div>
                <Label htmlFor="confirmation-text">
                  Digite exatamente: <code className="bg-muted px-1 rounded">{REQUIRED_CONFIRMATION}</code> <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="confirmation-text"
                  value={confirmationText}
                  onChange={(e) => setConfirmationText(e.target.value)}
                  placeholder={REQUIRED_CONFIRMATION}
                />
              </div>

              <div>
                <Label htmlFor="reason">Motivo (opcional)</Label>
                <Textarea
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Informe o motivo para a exclusão da conta (opcional)"
                  rows={3}
                />
              </div>
            </div>

            <div className="flex gap-4">
              <Button 
                onClick={submitDeletionRequest}
                disabled={!canProceedToConfirmation || isLoading}
                variant="destructive"
                className="gap-2"
              >
                <Trash2 className="h-4 w-4" />
                {isLoading ? 'Processando...' : 'Confirmar Exclusão Definitiva'}
              </Button>
              <Button variant="outline" onClick={() => setStep('summary')}>
                Voltar
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Processing */}
        {step === 'processing' && (
          <div className="space-y-6 text-center">
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600"></div>
            </div>
            <div>
              <h4 className="font-medium">Processando Exclusão de Dados</h4>
              <p className="text-sm text-muted-foreground mt-2">
                Seus dados estão sendo removidos permanentemente do sistema. 
                Este processo pode levar alguns minutos.
              </p>
            </div>
          </div>
        )}

        {/* Step 5: Completed */}
        {step === 'completed' && deletionResult && (
          <div className="space-y-6">
            <Alert>
              <Shield className="h-4 w-4" />
              <AlertTitle>Exclusão Concluída</AlertTitle>
              <AlertDescription>
                Seus dados foram excluídos com sucesso conforme a LGPD. 
                Você será redirecionado automaticamente em alguns segundos.
              </AlertDescription>
            </Alert>

            <div className="space-y-4">
              <div>
                <h5 className="font-medium">Resumo da Exclusão:</h5>
                <div className="text-sm text-muted-foreground mt-2">
                  <div>ID da Exclusão: <code>{deletionResult.deletion_id}</code></div>
                  <div>Data: {new Date(deletionResult.deleted_at).toLocaleString('pt-BR')}</div>
                  <div>Registros excluídos: {Object.values(deletionResult.summary.deleted_records).reduce((a, b) => a + b, 0)}</div>
                  <div>Registros anonimizados: {deletionResult.summary.anonymized_records}</div>
                </div>
              </div>

              <div className="text-xs text-muted-foreground">
                <p><strong>Conformidade LGPD:</strong> {deletionResult.lgpd_compliance.article}</p>
                <p><strong>Método:</strong> {deletionResult.lgpd_compliance.method}</p>
              </div>
            </div>

            <div className="text-center">
              <Button onClick={() => window.location.href = '/'}>
                Ir para Página Inicial
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}