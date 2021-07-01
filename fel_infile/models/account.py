# -*- encoding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round

from datetime import datetime
import base64
from lxml import etree
import requests
import re

#from import XMLSigner

import logging

class AccountMove(models.Model):
    _inherit = "account.move"

    pdf_fel = fields.Char('PDF FEL', copy=False)
    
    def _post(self, soft=True):
        if self.certificar():
            return super(AccountMove, self)._post(soft)

    def post(self):
        if self.certificar():
            return super(AccountMove, self).post()
    
    def certificar(self):
        for factura in self:
            if factura.requiere_certificacion():
                self.ensure_one()

                if factura.error_pre_validacion():
                    return False
                
                dte = factura.dte_documento()
                logging.warn(dte)
                xmls = etree.tostring(dte, encoding="UTF-8")
                xmls = xmls.decode("utf-8").replace("&amp;", "&").encode("utf-8")
                xmls_base64 = base64.b64encode(xmls)
                logging.warn(xmls)

                headers = { "Content-Type": "application/json" }
                data = {
                    "llave": factura.company_id.token_firma_fel,
                    "archivo": xmls_base64.decode("utf-8"),
                    "codigo": factura.company_id.vat.replace('-',''),
                    "alias": factura.company_id.usuario_fel,
                }
                r = requests.post('https://signer-emisores.feel.com.gt/sign_solicitud_firmas/firma_xml', json=data, headers=headers)
                logging.warn(r.text)
                firma_json = r.json()
                if firma_json["resultado"]:

                    headers = {
                        "USUARIO": factura.company_id.usuario_fel,
                        "LLAVE": factura.company_id.clave_fel,
                        "IDENTIFICADOR": factura.journal_id.code+str(factura.id),
                        "Content-Type": "application/json",
                    }
                    data = {
                        "nit_emisor": factura.company_id.vat.replace('-',''),
                        "correo_copia": factura.company_id.email,
                        "xml_dte": firma_json["archivo"]
                    }
                    r = requests.post("https://certificador.feel.com.gt/fel/certificacion/v2/dte/", json=data, headers=headers)
                    logging.warn(r.json())
                    certificacion_json = r.json()
                    if certificacion_json["resultado"]:
                        factura.firma_fel = certificacion_json["uuid"]
                        factura.ref = str(certificacion_json["serie"])+"-"+str(certificacion_json["numero"])
                        factura.serie_fel = certificacion_json["serie"]
                        factura.numero_fel = certificacion_json["numero"]
                        factura.documento_xml_fel = xmls_base64
                        factura.resultado_xml_fel = certificacion_json["xml_certificado"]
                        factura.pdf_fel = "https://report.feel.com.gt/ingfacereport/ingfacereport_documento?uuid="+certificacion_json["uuid"]
                        factura.certificador_fel = "infile"
                    else:
                        factura.error_certificador(str(certificacion_json["descripcion_errores"]))
                        return False
                        
                else:
                    factura.error_certificador(r.text)
                    return False

        return True
        
    def button_cancel(self):
        result = super(AccountMove, self).button_cancel()
        for factura in self:
            if factura.requiere_certificacion() and factura.firma_fel:
                dte = factura.dte_anulacion()
                
                xmls = etree.tostring(dte, encoding="UTF-8")
                xmls = xmls.decode("utf-8").replace("&amp;", "&").encode("utf-8")
                xmls_base64 = base64.b64encode(xmls)
                logging.warn(xmls)

                headers = { "Content-Type": "application/json" }
                data = {
                    "llave": factura.company_id.token_firma_fel,
                    "archivo": xmls_base64.decode("utf-8"),
                    "codigo": factura.company_id.vat.replace('-',''),
                    "alias": factura.company_id.usuario_fel,
                }
                r = requests.post('https://signer-emisores.feel.com.gt/sign_solicitud_firmas/firma_xml', json=data, headers=headers)
                logging.warn(r.text)
                firma_json = r.json()
                if firma_json["resultado"]:

                    headers = {
                        "USUARIO": factura.company_id.usuario_fel,
                        "LLAVE": factura.company_id.clave_fel,
                        "IDENTIFICADOR": factura.journal_id.code+str(factura.id),
                        "Content-Type": "application/json",
                    }
                    data = {
                        "nit_emisor": factura.company_id.vat.replace('-',''),
                        "correo_copia": factura.company_id.email,
                        "xml_dte": firma_json["archivo"]
                    }
                    r = requests.post("https://certificador.feel.com.gt/fel/anulacion/v2/dte/", json=data, headers=headers)
                    logging.warn(r.text)
                    certificacion_json = r.json()
                    if not certificacion_json["resultado"]:
                        raise UserError(str(certificacion_json["descripcion_errores"]))
                else:
                    raise UserError(r.text)

class AccountJournal(models.Model):
    _inherit = "account.journal"

class ResCompany(models.Model):
    _inherit = "res.company"

    usuario_fel = fields.Char('Usuario FEL')
    clave_fel = fields.Char('Clave FEL')
    token_firma_fel = fields.Char('Token Firma FEL')
