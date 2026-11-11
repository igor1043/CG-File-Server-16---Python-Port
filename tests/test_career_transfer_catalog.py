import copy
import tempfile
import unittest
from pathlib import Path

import test_career_overlay as fixtures
from server16_py.career_transfer_catalog import transfer_catalog,country_name


def with_regions(data):
    data=copy.deepcopy(data)
    for index,(country,name) in enumerate(((156,'Brasil Sudeste'),(217,'Brasil Sul'),
            (220,'Brasil Norte-Centro'),(221,'Brasil Nordeste'),(223,'Brasil Nordeste 2'),
            (224,'Brasil Norte-Centro 2'),(226,'Brasil Norte-Centro 3'),(255,'255'),(241,''))):
        league=1000+index;team=2000+index
        if name:data['nations'][str(country)]=name
        data['leagues'].append(dict(id=league,name='Federação regional',country_id=country,level=1))
        data['teams'].append(dict(id=team,name='Clube regional',asset_id=team))
        data['links'].append((league,team))
        # A real domestic member must remain available through its national league.
        data['links'].append((league,101))
    data['nations']['21']='Germany'
    data['leagues'].append(dict(id=19,name='Bundesliga',country_id=21,level=1))
    data['teams'].append(dict(id=3000,name='Clube alemão',asset_id=3000))
    data['links'].append((19,3000))
    return data


def catalog():
    leagues=[(7,'Série A',54,1),(83,'Série B',54,2),(350,'Série C',54,3),
             (351,'Série D',54,4),(354,'Brasileir�o Divis�o de Acesso',54,5),
             (78,'International',75,5),(382,'Free Agents League',210,1),
             (62,'England National League (5)',14,5)]
    teams=[(101,'Internacional'),(102,'Brasil de Pelotas'),(103,'Clube C'),(104,'Clube D'),
           (105,'Clube de acesso'),(1370,'Brazil'),(111592,'NG - FA'),(106,'English Club')]
    return {'nations':{'54':'Brasil','75':'International','210':'Free Agents','14':'England'},
        'nation_codes':{},'leagues':[dict(id=i,name=n,country_id=c,level=l) for i,n,c,l in leagues],
        'teams':[dict(id=i,name=n,asset_id=i) for i,n in teams],
        'links':[(7,101),(83,102),(350,103),(351,104),(354,105),(78,1370),(382,111592),(62,106)]}


class TransferCatalogTests(unittest.TestCase):
    def test_regional_and_unidentified_destinations_are_removed_without_losing_national_clubs(self):
        data=with_regions(catalog());before=copy.deepcopy(data);result=transfer_catalog(data)
        self.assertEqual({'54':'Brasil','14':'Inglaterra','21':'Alemanha'},result['nations'])
        self.assertTrue(all(league<1000 for league,team in result['links']))
        self.assertIn((7,101),result['links'])
        self.assertTrue(all(team<2000 or team==3000 for team in (r['id'] for r in result['teams'])))
        self.assertEqual(before,data)

    def test_save_without_nation_table_uses_reference_only_for_country_identity(self):
        base=with_regions(catalog());career=copy.deepcopy(base);career['nations']={}
        career['links']=[(351,team) if league==354 else (league,team) for league,team in career['links']]
        result=transfer_catalog(career,base)
        self.assertEqual({'54','14','21'},set(result['nations']))
        self.assertIn((351,105),result['links'])
        self.assertNotIn((354,105),result['links'])

    def test_internal_country_groups_are_not_domestic_career_destinations(self):
        data=catalog()
        for ident,name in ((0,'Generic'),(255,'Brasil'),(211,'Rest of World')):
            with self.subTest(country=ident):
                current=copy.deepcopy(data);current['nations'][str(ident)]=name
                current['leagues'][0]['country_id']=ident
                result=transfer_catalog(current)
                self.assertNotIn(7,{r['id'] for r in result['leagues']})

    def test_new_registered_countries_remain_expandable(self):
        data=catalog();data['nations']['240']='Timor-Leste'
        data['leagues'][0]['country_id']=240
        self.assertIn((7,101),transfer_catalog(data)['links'])
        self.assertEqual('Timor-Leste',transfer_catalog(data)['nations']['240'])
        for value in ('Germany',' germany ','GERMANY','Alemanha'):
            self.assertEqual('Alemanha',country_name(value))

    def test_retains_series_a_to_d_and_real_fifth_division_without_mutating_source(self):
        original=catalog();before=copy.deepcopy(original);result=transfer_catalog(original)
        self.assertEqual({r['id'] for r in result['leagues']},{7,83,350,351,62})
        self.assertEqual({r['id'] for r in result['teams']},{101,102,103,104,106})
        self.assertEqual(original,before)

    def test_promoted_access_club_is_available_in_current_serie_d(self):
        base=catalog();career=copy.deepcopy(base)
        career['links']=[(351,team) if league==354 else (league,team) for league,team in career['links']]
        result=transfer_catalog(career,base)
        self.assertIn((351,105),result['links'])
        self.assertIn(105,{r['id'] for r in result['teams']})
        self.assertNotIn(354,{r['id'] for r in result['leagues']})

    def test_national_and_free_agent_teams_stay_excluded_even_with_domestic_links(self):
        base=catalog();career=copy.deepcopy(base)
        career['links']=[(7,team) if league in (78,382) else (league,team) for league,team in career['links']]
        result=transfer_catalog(career,base)
        self.assertNotIn(1370,{r['id'] for r in result['teams']})
        self.assertNotIn(111592,{r['id'] for r in result['teams']})

    def test_named_access_divisions_and_localized_non_club_groups(self):
        for name in ('DIVISÃO DE ACESSO','Divisão de acesso regional','Division de acceso','Access Division'):
            with self.subTest(name=name):
                data=catalog();data['leagues'][4].update(id=900,name=name)
                data['links'][4]=(900,105)
                self.assertNotIn(900,{r['id'] for r in transfer_catalog(data)['leagues']})
        data=catalog();data['leagues'][5].update(id=901,name='Seleções nacionais');data['links'][5]=(901,1370)
        self.assertNotIn(901,{r['id'] for r in transfer_catalog(data)['leagues']})

    def test_panel_countries_and_teams_use_same_filtered_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
            try:
                svc.catalog=catalog();svc.inspection['catalog']=copy.deepcopy(svc.catalog)
                selector.open(career=True);panel=selector.career_panel
                self.assertEqual({r[0] for r in panel.countries()},{54,14})
                panel.country=54;panel.reset_filters()
                self.assertEqual({r['id'] for r in panel.leagues()},{7,83,350,351})
                first=panel.data();self.assertIs(first,panel.data())
                changed=copy.deepcopy(svc.inspection['catalog']);changed['links'][4]=(351,105)
                svc.inspection['catalog']=changed
                self.assertIsNot(first,panel.data())
                panel.league=351
                self.assertIn(105,{r['id'] for r in panel.teams()})
            finally:selector.shutdown()

    def test_filtered_destinations_cannot_be_requested_through_service(self):
        with tempfile.TemporaryDirectory() as temp:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
            try:
                svc.catalog=with_regions(catalog());svc.inspection['catalog']=copy.deepcopy(svc.catalog)
                for league,team in ((354,105),(78,1370),(382,111592),*[(1000+i,2000+i) for i in range(9)]):
                    with self.subTest(league=league),self.assertRaises(ValueError):
                        svc.confirm('transfer',team_id=team,league_id=league)
                    self.assertIsNone(svc.pending)
                svc.jobs_runtime.request.assert_not_called()
                svc.confirm('transfer',team_id=104,league_id=351)
                self.assertEqual(svc.pending['team_id'],104)
            finally:selector.shutdown()

    def test_panel_labels_use_the_localized_safe_country_list(self):
        with tempfile.TemporaryDirectory() as temp:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
            try:
                svc.catalog=with_regions(catalog());svc.inspection['catalog']=copy.deepcopy(svc.catalog)
                selector.open(career=True);panel=selector.career_panel
                self.assertEqual(dict(panel.countries()),{54:'Brasil',14:'Inglaterra',21:'Alemanha'})
                panel.country=217;panel.reset_filters()
                self.assertIn(panel.country,(54,14,21))
            finally:selector.shutdown()
