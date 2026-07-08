// UNIVAQ DIIIE - funzionalita' admin custom, non presente in Overleaf upstream.
// Copiato integralmente (nuovo file, nessuna sovrascrittura) dentro
// services/web/app/src/Features/ServerAdmin/ dal workflow GitHub Actions
// (vedi raspberrypi/patches/overleaf-admin-purge/apply-patch.py).
//
// ESM (.mjs): il fork yu-i-i/overleaf-cep (tag v6.1.0-ext-v4.1) ha
// migrato models/Project, models/User, Authentication/SessionManager e
// Project/ProjectDeleter a moduli ES (.mjs, "import"/"export"), quindi
// questo file non puo' usare require()/module.exports (fallirebbe con
// ERR_REQUIRE_ESM). Verificato dal vivo sui sorgenti del tag.
//
// Riusa esclusivamente API reali e gia' testate di Overleaf per la
// cancellazione progetti (ProjectDeleter), la stessa logica usata dal
// cestino a 90 giorni: non manipola mai direttamente Mongo/filestore.
//
// Flusso in due passi per sicurezza:
//   1. preview  - trova i progetti con lastUpdated < data indicata, NESSUNA modifica
//   2. execute  - richiede di scrivere "CONFERMA" e ri-verifica il conteggio
//                 prima di procedere davvero

import logger from '@overleaf/logger'
import { Project } from '../../models/Project.mjs'
import { User } from '../../models/User.mjs'
import SessionManager from '../Authentication/SessionManager.mjs'
import ProjectDeleter from '../Project/ProjectDeleter.mjs'

const MAX_PREVIEW_ROWS = 500

async function findOldProjects(cutoffDate) {
  return Project.find(
    { lastUpdated: { $lt: cutoffDate } },
    { _id: 1, name: 1, lastUpdated: 1, owner_ref: 1 }
  )
    .sort({ lastUpdated: 1 })
    .exec()
}

function parseCutoffDate(value) {
  if (!value) return null
  const date = new Date(value)
  if (isNaN(date.getTime())) return null
  return date
}

const PurgeOldProjectsController = {
  form(req, res) {
    res.render('admin/purge-old-projects', {})
  },

  preview(req, res, next) {
    const cutoffDateStr = req.body.cutoff_date
    const hardDelete = req.body.hard_delete === 'on'
    const cutoffDate = parseCutoffDate(cutoffDateStr)

    if (!cutoffDate) {
      return res.render('admin/purge-old-projects', {
        purgeError: 'Data non valida. Usa il selettore data.',
      })
    }

    findOldProjects(cutoffDate)
      .then(async projects => {
        const truncated = projects.length > MAX_PREVIEW_ROWS
        const shown = projects.slice(0, MAX_PREVIEW_ROWS)
        const ownerIds = [
          ...new Set(
            shown
              .map(p => p.owner_ref && p.owner_ref.toString())
              .filter(Boolean)
          ),
        ]
        const owners = await User.find(
          { _id: { $in: ownerIds } },
          { email: 1 }
        ).exec()
        const emailById = new Map(
          owners.map(u => [u._id.toString(), u.email])
        )
        const rows = shown.map(p => ({
          id: p._id.toString(),
          name: p.name,
          lastUpdated: p.lastUpdated
            ? p.lastUpdated.toISOString().slice(0, 10)
            : '-',
          ownerEmail:
            (p.owner_ref && emailById.get(p.owner_ref.toString())) ||
            '(proprietario sconosciuto/cancellato)',
        }))

        res.render('admin/purge-old-projects', {
          purgePreview: {
            cutoffDateStr,
            hardDelete,
            count: projects.length,
            truncated,
            rows,
          },
        })
      })
      .catch(next)
  },

  execute(req, res, next) {
    const cutoffDateStr = req.body.cutoff_date
    const hardDelete = req.body.hard_delete === 'on'
    const confirmationText = (req.body.confirmation_text || '').trim()
    const expectedCount = parseInt(req.body.expected_count, 10)
    const cutoffDate = parseCutoffDate(cutoffDateStr)

    if (confirmationText !== 'CONFERMA') {
      return res.render('admin/purge-old-projects', {
        purgeError:
          'Devi scrivere esattamente CONFERMA nel campo di conferma per procedere. Nessun progetto e\' stato toccato.',
      })
    }
    if (!cutoffDate) {
      return res.render('admin/purge-old-projects', {
        purgeError: 'Data non valida. Rifai l\'anteprima.',
      })
    }

    findOldProjects(cutoffDate)
      .then(async projects => {
        if (!isNaN(expectedCount) && projects.length !== expectedCount) {
          return res.render('admin/purge-old-projects', {
            purgeError: `Il numero di progetti corrispondenti e' cambiato dall'anteprima (era ${expectedCount}, ora ${projects.length}). Per sicurezza, rifai l'anteprima prima di confermare.`,
          })
        }

        const admin = SessionManager.getSessionUser(req.session)
        const deleted = []
        const failed = []

        for (const project of projects) {
          try {
            await ProjectDeleter.promises.deleteProject(project._id, {
              deleterUser: admin,
            })
            if (hardDelete) {
              await ProjectDeleter.promises.expireDeletedProject(project._id)
            }
            deleted.push({ id: project._id.toString(), name: project.name })
          } catch (err) {
            logger.error(
              { err, projectId: project._id },
              'purge-old-projects: failed to delete project'
            )
            failed.push({
              id: project._id.toString(),
              name: project.name,
              error: err.message,
            })
          }
        }

        logger.warn(
          {
            admin: admin && admin.email,
            cutoffDateStr,
            hardDelete,
            deletedCount: deleted.length,
            failedCount: failed.length,
          },
          'admin purge-old-projects executed'
        )

        res.render('admin/purge-old-projects', {
          purgeResult: { hardDelete, deleted, failed },
        })
      })
      .catch(next)
  },
}

export default PurgeOldProjectsController
