(() => {
 const shell=document.querySelector('[data-results-published]');
 const wasPublished=shell?.dataset.resultsPublished==='true';
 const original=App.eventState?.event_status;
 document.addEventListener('eventstate',e=>{if((e.detail.results_published&&!wasPublished)||(original&&original!=='COMPLETED'&&e.detail.event_status==='COMPLETED'))location.reload();});
})();
